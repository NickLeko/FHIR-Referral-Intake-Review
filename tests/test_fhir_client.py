from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from src.fhir_client import (
    DEFAULT_FHIR_BASE_URL,
    FHIRClient,
    FHIRNotFoundError,
    FHIRReferenceError,
    FHIRResponseError,
)
from src.utils import load_json_file


class FakeResponse:
    def __init__(self, status_code: int, payload, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.closed = False

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = deque(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        return item


def _patient() -> dict:
    return load_json_file(
        Path("tests/fixtures/fhir_responses/Patient-pat-recorded.json")
    )


def test_get_resource_uses_safe_read_headers_and_records_provenance() -> None:
    session = FakeSession([FakeResponse(200, _patient())])
    client = FHIRClient(
        base_url="https://example.test/fhir/",
        session=session,
        clock=lambda: datetime(2026, 8, 21, 9, 30, tzinfo=timezone.utc),
    )

    fetched = client.get_resource("Patient", "pat-recorded")

    assert session.calls == [
        {
            "url": "https://example.test/fhir/Patient/pat-recorded",
            "headers": {
                "Accept": "application/fhir+json",
                "User-Agent": "FHIR-Referral-Intake-Review/1.0",
            },
            "timeout": 10.0,
            "allow_redirects": False,
        }
    ]
    assert fetched.provenance.to_dict() == {
        "server_base_url": "https://example.test/fhir",
        "resource_type": "Patient",
        "resource_id": "pat-recorded",
        "version_id": "3",
        "last_updated": "2026-08-19T10:00:00Z",
        "fetched_at": "2026-08-21T09:30:00+00:00",
    }


def test_client_retries_transient_failures_but_not_not_found() -> None:
    session = FakeSession(
        [
            FakeResponse(503, {"resourceType": "OperationOutcome"}),
            requests.Timeout("offline"),
            FakeResponse(200, _patient()),
        ]
    )
    delays: list[float] = []
    client = FHIRClient(
        base_url="https://example.test/fhir",
        session=session,
        sleep=delays.append,
        retry_backoff=0.1,
    )

    assert (
        client.get_resource("Patient", "pat-recorded").resource["id"]
        == "pat-recorded"
    )
    assert len(session.calls) == 3
    assert delays == [0.1, 0.2]

    not_found_session = FakeSession([FakeResponse(404, {})])
    not_found_client = FHIRClient(
        base_url="https://example.test/fhir",
        session=not_found_session,
    )
    with pytest.raises(FHIRNotFoundError):
        not_found_client.get_resource("Patient", "pat-recorded")
    assert len(not_found_session.calls) == 1


def test_reference_resolution_accepts_local_absolute_and_rejects_cross_origin() -> None:
    session = FakeSession([FakeResponse(200, _patient())])
    client = FHIRClient(base_url="https://example.test/fhir", session=session)

    client.get_reference(
        "https://example.test/fhir/Patient/pat-recorded",
        expected_types=("Patient",),
    )
    with pytest.raises(FHIRReferenceError):
        client.get_reference(
            "https://other.test/fhir/Patient/pat-recorded",
            expected_types=("Patient",),
        )
    assert len(session.calls) == 1


def test_client_rejects_malformed_payload_without_exposing_it() -> None:
    session = FakeSession([FakeResponse(200, ["untrusted", "payload"])])
    client = FHIRClient(base_url="https://example.test/fhir", session=session)

    with pytest.raises(FHIRResponseError, match="top level is not an object") as error:
        client.get_resource("Patient", "pat-recorded")

    assert "untrusted" not in str(error.value)


def test_base_url_defaults_from_environment(monkeypatch) -> None:
    monkeypatch.delenv("FHIR_BASE_URL", raising=False)
    client = FHIRClient(session=FakeSession([FakeResponse(200, _patient())]))

    assert client.base_url == DEFAULT_FHIR_BASE_URL


def test_search_bundle_follows_only_same_base_next_links() -> None:
    search_bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [],
        "link": [],
    }
    session = FakeSession(
        [FakeResponse(200, search_bundle), FakeResponse(200, search_bundle)]
    )
    client = FHIRClient(base_url="https://example.test/fhir", session=session)

    assert client.get_search_bundle("ServiceRequest", count=7) == search_bundle
    assert (
        session.calls[0]["url"]
        == "https://example.test/fhir/ServiceRequest?_count=7"
    )
    assert client.get_search_bundle(
        "ServiceRequest",
        page_url="https://example.test/fhir?_getpages=next-token",
    ) == search_bundle
    with pytest.raises(FHIRReferenceError):
        client.get_search_bundle(
            "ServiceRequest",
            page_url="https://other.test/fhir?_getpages=next-token",
        )
    assert len(session.calls) == 2
