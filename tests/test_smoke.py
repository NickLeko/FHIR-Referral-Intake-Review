from __future__ import annotations

import pytest

from src.mapping import build_review_packet
from src.parser import BundleValidationError, parse_bundle


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


def test_malformed_input_fails_safely() -> None:
    malformed_bundle = {"resourceType": "Bundle", "id": "bad-bundle", "entry": [{}]}

    with pytest.raises(BundleValidationError):
        parse_bundle(malformed_bundle)
