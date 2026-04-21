from __future__ import annotations

import pytest

from src.mapping import build_review_packet
from src.parser import BundleValidationError, parse_bundle
from src.review import HumanReviewDecision, build_reviewed_output


def _first_resource(bundle: dict, resource_type: str) -> dict:
    return next(
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    )


def test_complete_bundle_maps_correctly(sample_bundle_dir, load_sample_bundle) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status.value == "REVIEW_READY"
    assert packet.requested_service == "Cardiology consultation"
    assert packet.ordering_provider == "Riley Chen, MD"
    assert "R06.09 - Exertional dyspnea" in packet.supporting_diagnosis


def test_incomplete_bundle_flags_missing_fields(sample_bundle_dir, load_sample_bundle) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status.value == "INCOMPLETE"
    assert "ordering_provider" in packet.missing_elements
    assert "encounter_context" in packet.missing_elements
    assert "supporting_diagnosis" in packet.missing_elements


def test_ambiguous_bundle_requires_human_confirmation(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_003_human_confirmation.json")
    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status.value == "HUMAN_CONFIRMATION_REQUIRED"
    assert "requested_service" in packet.ambiguous_elements
    assert "ordering_provider" in packet.fields_requiring_human_confirmation


def test_traceability_entries_are_produced(sample_bundle_dir, load_sample_bundle) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    packet = build_review_packet(parse_bundle(bundle))

    assert packet.source_trace["requested_service"]
    assert packet.source_trace["ordering_provider"]
    assert packet.source_trace["supporting_diagnosis"]


def test_full_url_references_are_resolved(sample_bundle_dir, load_sample_bundle) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    service_request = _first_resource(bundle, "ServiceRequest")
    service_request["subject"]["reference"] = "urn:uuid:patient-001"
    service_request["requester"]["reference"] = "urn:uuid:practitioner-001"
    service_request["encounter"]["reference"] = "urn:uuid:encounter-001"
    service_request["reasonReference"][0]["reference"] = "urn:uuid:condition-001"
    service_request["supportingInfo"][0]["reference"] = "urn:uuid:observation-001"
    service_request["supportingInfo"][1]["reference"] = "urn:uuid:document-001"

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status.value == "REVIEW_READY"
    assert packet.patient_age_group == "Adult"
    assert packet.ordering_provider == "Riley Chen, MD"
    assert packet.encounter_context == "Ambulatory | Cardiology clinic intake | 2026-02-28"
    assert packet.supporting_diagnosis == ["R06.09 - Exertional dyspnea"]
    assert packet.key_observations == ["Resting oxygen saturation: 94 %"]
    assert packet.referenced_documents == ["Outside stress test summary"]


def test_patient_is_resolved_from_service_request_subject(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    bundle["entry"].insert(
        0,
        {
            "fullUrl": "urn:uuid:patient-decoy",
            "resource": {
                "resourceType": "Patient",
                "id": "pat-decoy",
                "birthDate": "1930-01-01",
            },
        },
    )

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.patient_age_group == "Adult"
    assert packet.source_trace["patient_age_group"][0].resource_id == "pat-001"


def test_issue_rationales_explain_missing_and_ambiguous_fields(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    incomplete_bundle = load_sample_bundle(
        sample_bundle_dir / "bundle_002_incomplete.json"
    )
    incomplete_packet = build_review_packet(parse_bundle(incomplete_bundle))

    missing_ordering_provider = next(
        issue
        for issue in incomplete_packet.issue_rationales
        if issue.field == "ordering_provider"
    )
    assert missing_ordering_provider.issue_type == "missing"
    assert "ordering provider" in missing_ordering_provider.rationale
    assert missing_ordering_provider.evidence == "No value extracted."

    ambiguous_bundle = load_sample_bundle(
        sample_bundle_dir / "bundle_003_human_confirmation.json"
    )
    ambiguous_packet = build_review_packet(parse_bundle(ambiguous_bundle))
    ambiguous_requested_service = next(
        issue
        for issue in ambiguous_packet.issue_rationales
        if issue.field == "requested_service"
    )
    assert ambiguous_requested_service.issue_type == "ambiguous"
    assert ambiguous_requested_service.evidence == "Specialty consult"
    assert "ServiceRequest/sr-003.code.text" in ambiguous_requested_service.source


def test_review_override_requires_reviewer_note(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    packet = build_review_packet(parse_bundle(bundle))

    with pytest.raises(ValueError):
        build_reviewed_output(packet, HumanReviewDecision.CONFIRM_READY)


def test_unsupported_resource_gets_issue_rationale(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    bundle["entry"].append(
        {
            "resource": {
                "resourceType": "Coverage",
                "id": "coverage-001",
            }
        }
    )

    packet = build_review_packet(parse_bundle(bundle))
    unsupported_issue = next(
        issue for issue in packet.issue_rationales if issue.issue_type == "unsupported"
    )

    assert packet.status.value == "HUMAN_CONFIRMATION_REQUIRED"
    assert unsupported_issue.field == "Coverage/coverage-001"
    assert unsupported_issue.source == "Coverage/coverage-001"


def test_malformed_input_fails_safely() -> None:
    malformed_bundle = {"resourceType": "Bundle", "id": "bad-bundle", "entry": [{}]}

    with pytest.raises(BundleValidationError):
        parse_bundle(malformed_bundle)


def test_multiple_service_requests_fail_validation(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    bundle["entry"].append(
        {
            "fullUrl": "urn:uuid:servicerequest-extra",
            "resource": {
                "resourceType": "ServiceRequest",
                "id": "sr-extra",
                "status": "active",
                "intent": "order",
                "subject": {"reference": "Patient/pat-001"},
                "code": {"text": "Nephrology consultation"},
            },
        }
    )

    with pytest.raises(BundleValidationError, match="exactly one ServiceRequest"):
        parse_bundle(bundle)
