from __future__ import annotations

import pytest

from src.mapping import build_review_packet
from src.models import PacketStatus
from src.parser import parse_bundle


def _first_resource(bundle: dict, resource_type: str) -> dict:
    return next(
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    )


@pytest.mark.parametrize(
    ("filename", "expected_status", "missing_elements", "unsupported_elements"),
    [
        (
            "bundle_004_missing_requester.json",
            PacketStatus.INCOMPLETE,
            ["ordering_provider"],
            [],
        ),
        (
            "bundle_005_unresolved_diagnosis_reference.json",
            PacketStatus.INCOMPLETE,
            ["supporting_diagnosis"],
            [],
        ),
        (
            "bundle_006_ambiguous_payer_context.json",
            PacketStatus.HUMAN_CONFIRMATION_REQUIRED,
            [],
            ["Coverage/cov-006"],
        ),
        (
            "bundle_007_incomplete_patient_demographics.json",
            PacketStatus.INCOMPLETE,
            ["patient_age_group"],
            [],
        ),
    ],
)
def test_edge_case_sample_statuses_are_deterministic(
    sample_bundle_dir,
    load_sample_bundle,
    filename: str,
    expected_status: PacketStatus,
    missing_elements: list[str],
    unsupported_elements: list[str],
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / filename)
    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status == expected_status
    assert packet.missing_elements == missing_elements
    assert packet.unsupported_elements == unsupported_elements


def test_unresolved_reason_reference_does_not_fallback_to_unrelated_condition(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(
        sample_bundle_dir / "bundle_005_unresolved_diagnosis_reference.json"
    )
    packet = build_review_packet(parse_bundle(bundle))
    diagnosis_issue = next(
        issue for issue in packet.issue_rationales if issue.field == "supporting_diagnosis"
    )

    assert packet.supporting_diagnosis == []
    assert "supporting_diagnosis" not in packet.source_trace
    assert diagnosis_issue.issue_type == "missing"
    assert diagnosis_issue.source == "ServiceRequest.reasonReference"
    assert diagnosis_issue.evidence == (
        "Unresolved references: Condition/cond-005-missing"
    )


def test_partial_unresolved_reason_reference_requires_human_confirmation(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    service_request = _first_resource(bundle, "ServiceRequest")
    service_request["reasonReference"].append(
        {"reference": "Condition/cond-001-missing"}
    )

    packet = build_review_packet(parse_bundle(bundle))
    diagnosis_issue = next(
        issue
        for issue in packet.issue_rationales
        if issue.field == "supporting_diagnosis"
        and issue.issue_type == "ambiguous"
    )

    assert packet.status == PacketStatus.HUMAN_CONFIRMATION_REQUIRED
    assert packet.supporting_diagnosis == ["R06.09 - Exertional dyspnea"]
    assert "supporting_diagnosis" in packet.fields_requiring_human_confirmation
    assert diagnosis_issue.source == "ServiceRequest.reasonReference"
    assert diagnosis_issue.evidence == (
        "Unresolved references: Condition/cond-001-missing"
    )


def test_multiple_unreferenced_encounters_are_not_assumed(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    service_request = _first_resource(bundle, "ServiceRequest")
    service_request.pop("encounter")
    bundle["entry"].append(
        {
            "fullUrl": "urn:uuid:encounter-extra",
            "resource": {
                "resourceType": "Encounter",
                "id": "enc-extra",
                "status": "finished",
                "class": {
                    "code": "AMB",
                    "display": "Ambulatory"
                },
                "type": [
                    {
                        "text": "Unlinked administrative note"
                    }
                ],
                "period": {
                    "start": "2026-03-01"
                },
            },
        }
    )

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.status == PacketStatus.INCOMPLETE
    assert packet.encounter_context is None
    assert "encounter_context" in packet.missing_elements


def test_reason_reference_trace_is_preserved_for_supporting_diagnosis(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    packet = build_review_packet(parse_bundle(bundle))
    supporting_diagnosis_traces = packet.source_trace["supporting_diagnosis"]

    assert any(
        trace.resource_type == "ServiceRequest"
        and trace.resource_id == "sr-001"
        and trace.field_path == "reasonReference[0].reference"
        for trace in supporting_diagnosis_traces
    )
    assert any(
        trace.resource_type == "Condition"
        and trace.resource_id == "cond-001"
        and trace.field_path == "code"
        for trace in supporting_diagnosis_traces
    )


def test_single_unreferenced_condition_is_the_only_diagnosis_fallback(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    bundle["entry"].insert(
        -1,
        {
            "fullUrl": "urn:uuid:condition-only",
            "resource": {
                "resourceType": "Condition",
                "id": "cond-only",
                "clinicalStatus": "active",
                "code": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/sid/icd-10-cm",
                            "code": "M54.50",
                            "display": "Low back pain, unspecified",
                        }
                    ],
                    "text": "Low back pain",
                },
            },
        },
    )

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.supporting_diagnosis == ["M54.50 - Low back pain"]
    assert "supporting_diagnosis" not in packet.missing_elements


def test_multiple_unreferenced_conditions_are_not_used_as_supporting_diagnosis(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    bundle["entry"].insert(
        -1,
        {
            "fullUrl": "urn:uuid:condition-a",
            "resource": {
                "resourceType": "Condition",
                "id": "cond-a",
                "clinicalStatus": "active",
                "code": {"text": "Low back pain"},
            },
        },
    )
    bundle["entry"].insert(
        -1,
        {
            "fullUrl": "urn:uuid:condition-b",
            "resource": {
                "resourceType": "Condition",
                "id": "cond-b",
                "clinicalStatus": "active",
                "code": {"text": "Hip pain"},
            },
        },
    )

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.supporting_diagnosis == []
    assert "supporting_diagnosis" in packet.missing_elements


def test_unlinked_observations_and_documents_are_not_used_by_default(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    service_request = _first_resource(bundle, "ServiceRequest")
    service_request.pop("supportingInfo")
    bundle["entry"].insert(
        -1,
        {
            "fullUrl": "urn:uuid:observation-extra",
            "resource": {
                "resourceType": "Observation",
                "id": "obs-extra",
                "status": "final",
                "code": {"text": "Blood pressure"},
                "valueString": "120/80",
            },
        },
    )

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.key_observations == []
    assert packet.referenced_documents == []


def test_patient_age_group_uses_authored_on_before_bundle_timestamp(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    patient = _first_resource(bundle, "Patient")
    service_request = _first_resource(bundle, "ServiceRequest")
    patient["birthDate"] = "2008-03-15"
    service_request["authoredOn"] = "2026-03-01"
    bundle["timestamp"] = "2026-04-21T10:15:00Z"

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.patient_age_group == "Pediatric"
    assert any(
        trace.resource_type == "ServiceRequest"
        and trace.resource_id == "sr-001"
        and trace.field_path == "authoredOn"
        for trace in packet.source_trace["patient_age_group"]
    )


def test_patient_age_group_falls_back_to_bundle_timestamp_when_authored_on_missing(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    patient = _first_resource(bundle, "Patient")
    service_request = _first_resource(bundle, "ServiceRequest")
    patient["birthDate"] = "2008-03-15"
    service_request.pop("authoredOn")
    bundle["timestamp"] = "2026-03-01T10:15:00Z"

    packet = build_review_packet(parse_bundle(bundle))

    assert packet.patient_age_group == "Pediatric"
    assert any(
        trace.resource_type == "Bundle"
        and trace.resource_id == "bundle-001-review-ready"
        and trace.field_path == "timestamp"
        for trace in packet.source_trace["patient_age_group"]
    )
