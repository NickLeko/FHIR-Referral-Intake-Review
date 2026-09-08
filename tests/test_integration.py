from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import requests
from requests.adapters import BaseAdapter
from cryptography.hazmat.primitives import serialization

from scripts.setup_smart_sandbox import sandbox_environment
from src.auth import SmartClientCredentials, DEFAULT_SCOPES, FHIRAuthError
from src.contracts import reviewed_output_contract_errors
from src.fetch_and_review import fetch_review_packet, fetch_batch
from src.fhir_client import FHIRClient, FHIRConfigurationError, FHIRHTTPError
from src.models import HumanReviewDecision
from src.review import build_reviewed_output
from src.writeback import ReviewOutbox, ReviewGateError, review_task, IDENTIFIER_SYSTEM

BASE = "https://fhir.test/fhir"
TOKEN = "https://fhir.test/token"


class MockFHIRServer(BaseAdapter):
    """Stateful requests adapter: real prepared HTTP requests, no external network."""

    def __init__(self):
        self.calls = []
        self.faults = defaultdict(deque)
        self.tasks = {}
        self.resources = {}
        self.tokens = 0
        self.require_auth = False
        self.public_key = None
        self.assertions = []
        self.token_payload = None
        self.capability = {
            "resourceType": "CapabilityStatement",
            "rest": [
                {
                    "mode": "server",
                    "resource": [
                        {
                            "type": "Task",
                            "conditionalCreate": True,
                            "interaction": [
                                {"code": "create"},
                                {"code": "search-type"},
                            ],
                            "searchParam": [{"name": "identifier", "type": "token"}],
                        }
                    ],
                }
            ],
        }
        for name in ("one", "two", "three"):
            self.resources[f"ServiceRequest/{name}"] = {
                "resourceType": "ServiceRequest",
                "id": name,
                "status": "active",
                "intent": "order",
                "code": {"text": "Synthetic referral"},
                "authoredOn": "2026-08-20",
                "meta": {"versionId": "1"},
            }

    def close(self):
        pass

    def response(self, request, status=200, body=None, headers=None):
        result = requests.Response()
        result.status_code = status
        result._content = json.dumps(body).encode()
        result.headers.update(headers or {})
        result.request = request
        result.url = request.url
        return result

    def commit_task(self, request):
        condition = parse_qs(request.headers["If-None-Exist"])["identifier"][0]
        resource = json.loads(request.body)
        identifier = resource["identifier"][0]
        assert condition == f"{identifier['system']}|{identifier['value']}"
        if condition not in self.tasks:
            self.tasks[condition] = {**resource, "id": f"task-{len(self.tasks) + 1}"}
        return self.tasks[condition]

    def send(self, request, **kwargs):
        self.calls.append(request)
        path = urlsplit(request.url).path
        faults = self.faults[(request.method, path)]
        if faults:
            fault = faults.popleft()
            if fault == "commit_lost":
                self.commit_task(request)
                raise requests.Timeout("sensitive remote data must never escape")
            if fault == "crash_after_commit":
                self.commit_task(request)
                raise KeyboardInterrupt()
            if isinstance(fault, Exception):
                raise fault
            if isinstance(fault, tuple):
                return self.response(request, *fault)
            if isinstance(fault, int):
                return self.response(
                    request, fault, {"secret": "remote-sensitive-detail"}
                )
        if path == "/token":
            data = parse_qs(request.body)
            assert data["grant_type"] == ["client_credentials"]
            assert "refresh_token" not in data
            assertion = jwt.decode(
                data["client_assertion"][0],
                self.public_key,
                algorithms=["RS384"],
                audience=TOKEN,
            )
            assert assertion["iss"] == assertion["sub"]
            assert assertion["exp"] - assertion["iat"] == 300
            self.assertions.append(assertion)
            self.tokens += 1
            return self.response(
                request,
                body=self.token_payload
                or {
                    "access_token": f"test-token-{self.tokens}",
                    "token_type": "Bearer",
                    "expires_in": 60,
                    "scope": DEFAULT_SCOPES,
                },
            )
        if (
            self.require_auth
            and request.headers.get("Authorization")
            != f"Bearer test-token-{self.tokens}"
        ):
            return self.response(request, 401)
        if path == "/fhir/metadata":
            return self.response(request, body=self.capability)
        if path == "/fhir/Task":
            if request.method == "POST":
                return self.response(request, 201, self.commit_task(request))
            condition = parse_qs(urlsplit(request.url).query)["identifier"][0]
            matches = [self.tasks[condition]] if condition in self.tasks else []
            return self.response(
                request,
                body={
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "total": len(matches),
                    "entry": [{"resource": task} for task in matches],
                },
            )
        resource = self.resources.get(path.removeprefix("/fhir/"))
        return self.response(request, 200 if resource else 404, resource)


def make_client(server, **kwargs):
    session = requests.Session()
    session.mount("https://", server)
    return FHIRClient(
        BASE,
        session=session,
        token_provider=False,
        sleep=kwargs.pop("sleep", lambda _: None),
        **kwargs,
    )


@pytest.fixture
def server():
    return MockFHIRServer()


@pytest.fixture
def auth_client(server):
    config = sandbox_environment()
    client = make_client(server)
    private_key = serialization.load_pem_private_key(
        config["FHIR_PRIVATE_KEY_PEM"].encode(), password=None
    )
    server.public_key = private_key.public_key()
    server.require_auth = True
    clock = [1000.0]
    auth = SmartClientCredentials(
        client_id=config["FHIR_CLIENT_ID"],
        private_key=config["FHIR_PRIVATE_KEY_PEM"],
        key_id=config["FHIR_KEY_ID"],
        token_url=TOKEN,
        scopes=DEFAULT_SCOPES,
        request=client._request_with_retries,
        monotonic=lambda: clock[0],
    )
    client._token_provider = auth
    return client, clock


def reviewed(client, source_id="one", **kwargs):
    packet = fetch_review_packet(source_id, client=client)
    return build_reviewed_output(
        packet,
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        reviewer_name="Mock human reviewer",
        reviewed_at="2026-09-07T15:00:00+00:00",
        **kwargs,
    ).to_dict()


def queue(tmp_path, client, source_id="one"):
    outbox = ReviewOutbox(tmp_path / "outbox.sqlite3")
    payload = reviewed(client, source_id)
    row = outbox.enqueue(payload, base_url=BASE, output_dir=tmp_path / "reviews")
    return outbox, row, payload


def task_posts(server):
    return [
        r
        for r in server.calls
        if r.method == "POST" and urlsplit(r.url).path == "/fhir/Task"
    ]


def test_500_mid_read_batch_is_bounded_and_other_referrals_remain_unreviewed(
    server, tmp_path
):
    server.faults[("GET", "/fhir/ServiceRequest/two")].extend([500, 500, 500])
    client = make_client(server)
    results = fetch_batch(["one", "two", "three"], client=client, output_dir=tmp_path)
    assert [r["state"] for r in results] == [
        "awaiting_review",
        "needs_attention",
        "awaiting_review",
    ]
    assert not (tmp_path / "two_review_packet.json").exists()
    assert not task_posts(server)
    assert "human_review_decision" not in json.loads(
        (tmp_path / "one_review_packet.json").read_text()
    )
    assert len([r for r in server.calls if r.url.endswith("/two")]) == 3


def test_500_on_support_does_not_masquerade_as_missing_clinical_data(server, tmp_path):
    server.resources["ServiceRequest/one"]["subject"] = {"reference": "Patient/p"}
    server.faults[("GET", "/fhir/Patient/p")].extend([500] * 3)
    result = fetch_batch(["one"], client=make_client(server), output_dir=tmp_path)
    assert result[0]["state"] == "needs_attention"
    assert not (tmp_path / "one_review_packet.json").exists()


def test_token_expiry_between_read_and_write_reacquires_and_preserves_contract(
    server, auth_client, tmp_path
):
    client, clock = auth_client
    outbox, row, payload = queue(tmp_path, client)
    assert server.tokens == 1
    clock[0] += 60
    result = outbox.deliver(row["review_id"], client)
    assert result["state"] == "delivered"
    assert server.tokens == 2
    assert server.assertions[0]["jti"] != server.assertions[1]["jti"]
    saved = json.loads(Path(row["artifact_path"]).read_text())
    assert saved == payload
    assert reviewed_output_contract_errors(saved) == []
    task = next(iter(server.tasks.values()))
    assert task["focus"] == {"reference": "ServiceRequest/one"}
    assert (
        task["status"] == "completed" and task["businessStatus"]["text"] == "INCOMPLETE"
    )
    assert task_posts(server)[0].headers["Authorization"] == "Bearer test-token-2"
    assert "test-token" not in Path(outbox.path).read_bytes().decode(errors="ignore")


def test_unexpected_401_on_write_renews_once_and_repeats_same_conditional_create(
    server, auth_client, tmp_path
):
    client, _ = auth_client
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("POST", "/fhir/Task")].append(401)
    assert outbox.deliver(row["review_id"], client)["state"] == "delivered"
    posts = task_posts(server)
    assert len(posts) == 2 and server.tokens == 2
    assert posts[0].body == posts[1].body
    assert posts[0].headers["If-None-Exist"] == posts[1].headers["If-None-Exist"]
    assert len(server.tasks) == 1


def test_repeated_401_fails_closed_without_anonymous_fallback(server, auth_client):
    client, _ = auth_client
    server.faults[("GET", "/fhir/ServiceRequest/one")].extend([401, 401])
    with pytest.raises(FHIRHTTPError) as error:
        fetch_review_packet("one", client=client)
    assert error.value.status_code == 401 and server.tokens == 2
    assert all(
        r.headers.get("Authorization") for r in server.calls if "/fhir/" in r.url
    )


def test_lost_response_retries_conditional_create_and_creates_only_one_task(
    server, tmp_path
):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("POST", "/fhir/Task")].extend(["commit_lost"] * 3)
    result = outbox.deliver(row["review_id"], client)
    assert result["state"] == "delivered"
    assert len(server.tasks) == 1 and len(task_posts(server)) == 3
    restarted = ReviewOutbox(outbox.path)
    assert restarted.deliver(row["review_id"], client)["state"] == "delivered"
    assert len(task_posts(server)) == 3


def test_process_crash_after_commit_reconciles_without_new_post(server, tmp_path):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("POST", "/fhir/Task")].append("crash_after_commit")
    with pytest.raises(KeyboardInterrupt):
        outbox.deliver(row["review_id"], client)
    assert outbox.get(row["review_id"])["state"] == "uncertain"
    restarted = ReviewOutbox(outbox.path)
    assert restarted.deliver(row["review_id"], client)["state"] == "delivered"
    assert len(task_posts(server)) == len(server.tasks) == 1


def test_partial_write_batch_records_each_outcome_and_replay_skips_landed_writes(
    server, tmp_path
):
    client = make_client(server)
    outbox, first, _ = queue(tmp_path, client, "one")
    _, second, _ = queue(tmp_path, client, "two")
    _, third, _ = queue(tmp_path, client, "three")
    # First write succeeds, second fails through retry exhaustion, third succeeds.
    server.faults[("POST", "/fhir/Task")].extend([None, 500, 500, 500])
    keys = [r["review_id"] for r in (first, second, third)]
    results = outbox.deliver_batch(keys, client)
    assert [r["state"] for r in results] == ["delivered", "uncertain", "delivered"]
    assert len(server.tasks) == 2
    result = ReviewOutbox(outbox.path).deliver_batch(keys, client)
    assert all(r["state"] == "delivered" for r in result)
    assert len(server.tasks) == 3 and len(task_posts(server)) == 6


@pytest.mark.parametrize(
    "retry_after,expected",
    [
        ("2", [2.0, 0.5]),
        ("invalid", [0.25, 0.5]),
        ("Mon, 07 Sep 2026 00:00:03 GMT", [3.0, 0.5]),
    ],
)
def test_rate_limit_honors_retry_after_and_exponential_backoff(
    server, retry_after, expected
):
    delays = []
    client = make_client(
        server,
        sleep=delays.append,
        clock=lambda: datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    server.faults[("GET", "/fhir/ServiceRequest/one")].extend(
        [(429, {}, {"Retry-After": retry_after}), 429]
    )
    fetch_review_packet("one", client=client)
    assert delays == expected


def test_long_retry_after_defers_batch_and_survives_restart(server, tmp_path):
    client = make_client(server)
    outbox, first, _ = queue(tmp_path, client, "one")
    _, second, _ = queue(tmp_path, client, "two")
    server.faults[("POST", "/fhir/Task")].append((429, {}, {"Retry-After": "120"}))
    result = outbox.deliver_batch([first["review_id"], second["review_id"]], client)
    assert [r["state"] for r in result] == ["uncertain", "pending"]
    before = len(server.calls)
    ReviewOutbox(outbox.path).deliver(second["review_id"], make_client(server))
    assert len(server.calls) == before
    assert len(task_posts(server)) == 1


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"resourceType": "Bundle", "type": "collection", "entry": []},
        {"resourceType": "Bundle", "type": "searchset", "entry": {}},
        {"resourceType": "Bundle", "type": "searchset", "entry": [None]},
        {"resourceType": "Bundle", "type": "searchset", "link": ["bad"]},
    ],
)
def test_malformed_bundle_fails_closed_before_write(server, tmp_path, body):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("GET", "/fhir/Task")].append((200, body))
    result = outbox.deliver(row["review_id"], client)
    assert result["state"] == "needs_attention"
    assert not task_posts(server)


def test_wrong_root_bundle_shape_never_yields_reviewable_packet(server, tmp_path):
    server.faults[("GET", "/fhir/ServiceRequest/one")].append(
        (200, {"resourceType": "Bundle", "id": "one", "entry": []})
    )
    result = fetch_batch(["one"], client=make_client(server), output_dir=tmp_path)
    assert result[0]["state"] == "needs_attention"
    assert not (tmp_path / "one_review_packet.json").exists()


def test_uncertain_write_and_failed_reconciliation_requires_human_followup(
    server, tmp_path
):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("POST", "/fhir/Task")].extend(["commit_lost"] * 3)
    server.faults[("GET", "/fhir/Task")].extend([None, 500, 500, 500])
    result = outbox.deliver(row["review_id"], client)
    assert result["state"] == "uncertain"
    assert "human" in result["detail"].lower()
    assert "sensitive" not in result["detail"]
    assert len(server.tasks) == 1
    assert outbox.deliver(row["review_id"], client)["state"] == "delivered"
    assert len(server.tasks) == 1


def test_missing_conditional_create_capability_never_falls_back_to_plain_post(
    server, tmp_path
):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.capability["rest"][0]["resource"][0]["conditionalCreate"] = False
    assert outbox.deliver(row["review_id"], client)["state"] == "needs_attention"
    assert not task_posts(server)


def test_gate_rejects_unreviewed_mock_multi_source_wrong_destination_and_unexplained_override(
    server, tmp_path
):
    client = make_client(server)
    packet = fetch_review_packet("one", client=client)
    payload = reviewed(client)
    invalid = [packet.to_dict()]
    mock = deepcopy(payload)
    mock["extracted_review_packet"]["input_provenance"]["source_type"] = "mock"
    invalid.append(mock)
    multi = deepcopy(payload)
    multi["extracted_review_packet"]["input_provenance"]["resources"] *= 2
    invalid.append(multi)
    override = deepcopy(payload)
    override["human_review_decision"] = "CONFIRM_READY"
    override["final_status"] = "REVIEW_READY"
    invalid.append(override)
    for value in invalid:
        with pytest.raises(ReviewGateError):
            review_task(value, BASE)
    with pytest.raises(ReviewGateError):
        review_task(payload, "https://other.test/fhir")
    assert not task_posts(server)


def test_explicit_override_records_human_final_status(server, tmp_path):
    client = make_client(server)
    packet = fetch_review_packet("one", client=client)
    payload = build_reviewed_output(
        packet,
        HumanReviewDecision.CONFIRM_READY,
        reviewer_note="Mock reviewer verified missing context externally.",
        reviewer_name="Mock human",
    ).to_dict()
    outbox = ReviewOutbox(tmp_path / "outbox.sqlite3")
    row = outbox.enqueue(payload, base_url=BASE, output_dir=tmp_path)
    assert outbox.deliver(row["review_id"], client)["state"] == "delivered"
    task = next(iter(server.tasks.values()))
    assert task["businessStatus"]["text"] == "REVIEW_READY"
    assert task["output"][1]["valueString"] == "INCOMPLETE"


def test_modified_review_cannot_be_retried_under_original_key(server, tmp_path):
    client = make_client(server)
    outbox, row, payload = queue(tmp_path, client)
    payload["reviewer_name"] = "Different reviewer"
    Path(row["artifact_path"]).write_text(json.dumps(payload))
    assert outbox.deliver(row["review_id"], client)["state"] == "needs_attention"
    assert not task_posts(server)


def test_existing_conflicting_task_is_never_overwritten(server, tmp_path):
    client = make_client(server)
    outbox, row, payload = queue(tmp_path, client)
    key, task = review_task(payload, BASE)
    task["businessStatus"] = {"text": "OTHER"}
    server.tasks[f"{IDENTIFIER_SYSTEM}|{key}"] = {**task, "id": "conflict"}
    assert outbox.deliver(key, client)["state"] == "needs_attention"
    assert not task_posts(server)


@pytest.mark.parametrize(
    "payload",
    [
        {"access_token": "secret", "token_type": "Bearer", "expires_in": 0},
        {"access_token": "secret", "token_type": "Bearer", "expires_in": True},
        {
            "access_token": "secret",
            "token_type": "Bearer",
            "expires_in": 60,
            "scope": "system/Patient.rs",
        },
        {
            "access_token": "secret\r\nInjected",
            "token_type": "Bearer",
            "expires_in": 60,
        },
        {"access_token": "secret", "token_type": "Other", "expires_in": 60},
    ],
)
def test_invalid_token_response_never_reaches_fhir_or_exposes_secrets(
    server, auth_client, payload
):
    client, _ = auth_client
    server.token_payload = payload
    with pytest.raises(FHIRAuthError) as error:
        fetch_review_packet("one", client=client)
    assert "secret" not in str(error.value)
    assert len(server.calls) == 1


def test_token_endpoint_retries_and_fresh_assertion_each_attempt(server, auth_client):
    client, _ = auth_client
    server.faults[("POST", "/token")].extend([500, 500])
    fetch_review_packet("one", client=client)
    tokens = [
        parse_qs(r.body)["client_assertion"][0] for r in server.calls if r.url == TOKEN
    ]
    assert len(tokens) == len(set(tokens)) == 3


def test_auth_configuration_never_falls_back_to_open_access(monkeypatch):
    monkeypatch.setenv("FHIR_AUTH_MODE", "smart")
    monkeypatch.delenv("FHIR_PRIVATE_KEY_PEM", raising=False)
    with pytest.raises(FHIRConfigurationError):
        FHIRClient(BASE)
    monkeypatch.setenv("FHIR_AUTH_MODE", "none")
    monkeypatch.setenv("FHIR_CLIENT_ID", "configured-client")
    with pytest.raises(FHIRConfigurationError):
        FHIRClient(BASE)


def test_redirect_is_not_followed_with_credentials(server, auth_client):
    client, _ = auth_client
    server.faults[("GET", "/fhir/ServiceRequest/one")].append(
        (302, {}, {"Location": "https://untrusted.test"})
    )
    with pytest.raises(FHIRHTTPError):
        fetch_review_packet("one", client=client)
    assert all(urlsplit(r.url).hostname == "fhir.test" for r in server.calls)


def test_exhausted_rate_limit_does_not_immediately_send_next_batch_item(
    server, tmp_path
):
    delays = []
    client = make_client(server, sleep=delays.append)
    outbox, first, _ = queue(tmp_path, client, "one")
    _, second, _ = queue(tmp_path, client, "two")
    server.faults[("POST", "/fhir/Task")].extend([429] * 3)
    results = outbox.deliver_batch([first["review_id"], second["review_id"]], client)
    assert delays == [0.25, 0.5]
    assert len(task_posts(server)) == 3
    assert results[0]["state"] == "uncertain" and results[1]["state"] == "pending"
    assert results[1]["retry_at"] is not None


def test_invalid_client_grant_has_no_retry_or_anonymous_read(server, auth_client):
    client, _ = auth_client
    server.faults[("POST", "/token")].append(400)
    with pytest.raises(FHIRAuthError):
        fetch_review_packet("one", client=client)
    assert len(server.calls) == 1


def test_schema_failure_after_post_remains_uncertain_until_verified(server, tmp_path):
    client = make_client(server)
    outbox, row, _ = queue(tmp_path, client)
    server.faults[("GET", "/fhir/Task")].extend(
        [None, (200, {"resourceType": "Bundle", "entry": "invalid"})]
    )
    assert outbox.deliver(row["review_id"], client)["state"] == "uncertain"
    assert len(server.tasks) == 1
    assert outbox.deliver(row["review_id"], client)["state"] == "delivered"
    assert len(task_posts(server)) == 1


def test_local_save_failure_prevents_any_delivery(server, tmp_path, monkeypatch):
    client = make_client(server)
    outbox = ReviewOutbox(tmp_path / "outbox.sqlite3")
    payload = reviewed(client)

    def failed_save(*_):
        raise OSError("disk full")

    monkeypatch.setattr("src.writeback.save_json_file", failed_save)
    with pytest.raises(OSError):
        outbox.enqueue(payload, base_url=BASE, output_dir=tmp_path)
    assert not outbox.list() and not task_posts(server)


def test_batch_cli_reports_partial_delivery_and_replays_only_existing_reviews(
    server, tmp_path, monkeypatch, capsys
):
    from src import deliver_reviews

    client = make_client(server)
    outbox, first, _ = queue(tmp_path, client, "one")
    _, second, _ = queue(tmp_path, client, "two")
    server.faults[("POST", "/fhir/Task")].extend([None, 500, 500, 500])
    monkeypatch.setattr(deliver_reviews, "FHIRClient", lambda: client)
    args = ["--outbox", str(outbox.path), "--retry-pending"]
    assert deliver_reviews.main(args) == 1
    results = json.loads(capsys.readouterr().out)
    assert [r["state"] for r in results] == ["delivered", "uncertain"]
    assert deliver_reviews.main(args) == 0
    assert len(server.tasks) == 2
    assert len(outbox.list()) == 2
