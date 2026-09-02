from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from src.bundle_assembler import BundleAssembler
from src.fhir_client import FHIRNotFoundError, FetchedResource
from src.mapping import build_review_packet
from src.models import ResourceProvenance
from src.parser import parse_bundle
from src.utils import load_json_file


FIXTURE_DIR = Path("tests/fixtures/fhir_responses")
BASE_URL = "https://example.test/fhir"
FETCHED_AT = "2026-08-20T12:00:00+00:00"


class FixtureFHIRClient:
    def __init__(self, resources: dict[str, dict]) -> None:
        self.resources = resources
        self.calls: list[str] = []

    def get_resource(self, resource_type: str, resource_id: str) -> FetchedResource:
        return self._fetched(f"{resource_type}/{resource_id}")

    def get_reference(self, reference: str, expected_types) -> FetchedResource:
        parsed = urlsplit(reference)
        key = parsed.path.rsplit("/", 2)[-2:]
        resource_key = "/".join(key) if parsed.scheme else reference
        fetched = self._fetched(resource_key)
        assert fetched.resource["resourceType"] in set(expected_types)
        return fetched

    def _fetched(self, key: str) -> FetchedResource:
        self.calls.append(key)
        resource = deepcopy(self.resources.get(key))
        if resource is None:
            raise FHIRNotFoundError(404, f"{BASE_URL}/{key}", 1)
        meta = resource.get("meta") if isinstance(resource.get("meta"), dict) else {}
        return FetchedResource(
            resource=resource,
            request_url=f"{BASE_URL}/{key}",
            provenance=ResourceProvenance(
                server_base_url=BASE_URL,
                resource_type=resource["resourceType"],
                resource_id=resource["id"],
                version_id=meta.get("versionId"),
                last_updated=meta.get("lastUpdated"),
                fetched_at=FETCHED_AT,
            ),
        )


def _recorded_resources() -> dict[str, dict]:
    resource_files = {
        "ServiceRequest/sr-recorded": "ServiceRequest-sr-recorded.json",
        "Patient/pat-recorded": "Patient-pat-recorded.json",
        "Practitioner/prac-recorded": "Practitioner-prac-recorded.json",
        "Encounter/enc-recorded": "Encounter-enc-recorded.json",
        "Condition/cond-recorded": "Condition-cond-recorded.json",
        "Observation/obs-recorded": "Observation-obs-recorded.json",
        "DocumentReference/doc-recorded": "DocumentReference-doc-recorded.json",
    }
    return {
        key: load_json_file(FIXTURE_DIR / filename)
        for key, filename in resource_files.items()
    }


def test_assembler_builds_parser_compatible_live_bundle_with_provenance() -> None:
    client = FixtureFHIRClient(_recorded_resources())
    result = BundleAssembler(client).assemble("sr-recorded")
    packet = build_review_packet(parse_bundle(result.bundle))

    assert result.bundle["resourceType"] == "Bundle"
    assert result.bundle["type"] == "collection"
    assert result.bundle["timestamp"] == FETCHED_AT
    assert [entry["resource"]["resourceType"] for entry in result.bundle["entry"]] == [
        "Patient",
        "Practitioner",
        "Encounter",
        "Condition",
        "Condition",
        "Observation",
        "DocumentReference",
        "ServiceRequest",
    ]
    assert packet.status.value == "REVIEW_READY"
    assert packet.ordering_provider == "Synthetic Test Clinician"
    assert packet.referenced_documents == ["Synthetic outside referral summary"]
    assert result.input_provenance.source_type == "live"
    assert len(result.input_provenance.resources) == 7
    assert result.input_provenance.resources[0].resource_type == "ServiceRequest"
    assert result.input_provenance.scope_notes == [
        "Reverse references to this ServiceRequest were not searched or assembled."
    ]
    assert client.calls.count("Observation/obs-recorded") == 1


def test_unresolved_references_remain_in_the_service_request_and_use_existing_logic() -> None:
    resources = _recorded_resources()
    resources["ServiceRequest/sr-recorded"]["reasonReference"].append(
        {"reference": "Condition/missing"}
    )
    result = BundleAssembler(FixtureFHIRClient(resources)).assemble("sr-recorded")
    service_request = result.bundle["entry"][-1]["resource"]
    packet = build_review_packet(parse_bundle(result.bundle))

    assert service_request["reasonReference"][-1]["reference"] == "Condition/missing"
    assert any(issue.reference == "Condition/missing" for issue in result.issues)
    assert "supporting_diagnosis" in packet.fields_requiring_human_confirmation


def test_malformed_document_content_is_tolerated_without_rendering_payload() -> None:
    resources = _recorded_resources()
    resources["DocumentReference/doc-recorded"]["content"] = [None]

    result = BundleAssembler(FixtureFHIRClient(resources)).assemble("sr-recorded")
    packet = build_review_packet(parse_bundle(result.bundle))

    assert packet.referenced_documents == ["Synthetic outside referral summary"]


def test_out_of_scope_forward_reference_is_not_fetched_and_is_noted() -> None:
    resources = _recorded_resources()
    resources["ServiceRequest/sr-recorded"]["insurance"] = [
        {"reference": "Coverage/coverage-recorded"}
    ]
    client = FixtureFHIRClient(resources)

    result = BundleAssembler(client).assemble("sr-recorded")

    assert "Coverage/coverage-recorded" not in client.calls
    assert (
        "Ignored out-of-scope reference at ServiceRequest.insurance[0].reference."
        in result.input_provenance.scope_notes
    )
