from __future__ import annotations

from src.utils import list_sample_bundle_paths, load_json_file
from scripts.seed_sandbox import (
    SandboxSeeder,
    build_transaction_bundle,
    seed_all_sample_bundles,
)


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.closed = False

    def json(self) -> dict:
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_all_checked_in_bundles_convert_to_create_transactions() -> None:
    for bundle_path in list_sample_bundle_paths():
        source = load_json_file(bundle_path)
        transaction, service_request_index = build_transaction_bundle(source)

        assert transaction["type"] == "transaction"
        assert len(transaction["entry"]) == len(source["entry"])
        assert all(entry["request"]["method"] == "POST" for entry in transaction["entry"])
        assert all("id" not in entry["resource"] for entry in transaction["entry"])
        assert (
            transaction["entry"][service_request_index]["resource"]["resourceType"]
            == "ServiceRequest"
        )


def test_transaction_rewrites_relative_references_to_entry_full_urls() -> None:
    source = load_json_file(
        list_sample_bundle_paths()[0]
    )
    transaction, service_request_index = build_transaction_bundle(source)
    service_request = transaction["entry"][service_request_index]["resource"]
    full_urls = {
        entry["resource"]["resourceType"]: entry["fullUrl"]
        for entry in transaction["entry"]
    }

    assert service_request["subject"]["reference"] == full_urls["Patient"]
    assert service_request["requester"]["reference"] == full_urls["Practitioner"]
    assert service_request["reasonReference"][0]["reference"] == full_urls["Condition"]
    assert all(full_url.startswith("urn:uuid:") for full_url in full_urls.values())


def test_seeder_posts_once_and_extracts_transaction_service_request_id() -> None:
    source = load_json_file(list_sample_bundle_paths()[0])
    _, service_request_index = build_transaction_bundle(source)
    response_entries = [{} for _ in source["entry"]]
    response_entries[service_request_index] = {
        "response": {
            "status": "201 Created",
            "location": "ServiceRequest/server-assigned-123/_history/1",
        }
    }
    session = FakeSession(
        FakeResponse(
            {
                "resourceType": "Bundle",
                "type": "transaction-response",
                "entry": response_entries,
            }
        )
    )
    seeder = SandboxSeeder(base_url="https://example.test/fhir", session=session)

    assert seeder.seed_bundle(source) == "server-assigned-123"
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == "https://example.test/fhir"
    assert session.calls[0]["allow_redirects"] is False
    assert session.calls[0]["headers"]["Prefer"] == "return=minimal"


def test_seed_preserves_unresolved_reference_scenario_with_unique_missing_id() -> None:
    source = load_json_file(
        next(
            path
            for path in list_sample_bundle_paths()
            if path.name == "bundle_005_unresolved_diagnosis_reference.json"
        )
    )
    transaction, service_request_index = build_transaction_bundle(source)
    service_request = transaction["entry"][service_request_index]["resource"]

    assert service_request["reasonReference"][0]["reference"].startswith(
        "Condition/codex-missing-"
    )


def test_seed_all_processes_exactly_the_seven_checked_in_bundles() -> None:
    class RecordingSeeder:
        def __init__(self) -> None:
            self.calls = 0

        def seed_bundle(self, _bundle: dict) -> str:
            self.calls += 1
            return f"server-id-{self.calls}"

    seeder = RecordingSeeder()
    results = seed_all_sample_bundles(seeder)

    assert len(results) == 7
    assert seeder.calls == 7
