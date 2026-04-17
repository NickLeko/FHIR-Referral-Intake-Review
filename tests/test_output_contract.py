from __future__ import annotations

from pathlib import Path

from src.contracts import reviewed_output_contract_errors
from src.mapping import build_review_packet
from src.parser import parse_bundle
from src.review import HumanReviewDecision, build_reviewed_output
from src.utils import load_json_file


def test_reviewed_output_contract_accepts_generated_artifact(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_001_review_ready.json")
    packet = build_review_packet(parse_bundle(bundle))
    reviewed_output = build_reviewed_output(
        packet,
        HumanReviewDecision.CONFIRM_READY,
        reviewer_note="Reviewed as complete.",
        reviewed_at="2026-04-15T05:41:56+00:00",
    )

    assert reviewed_output_contract_errors(reviewed_output.to_dict()) == []


def test_reviewed_output_contract_rejects_mirror_mismatch(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    packet = build_review_packet(parse_bundle(bundle))
    reviewed_output = build_reviewed_output(
        packet,
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        reviewer_note="Still incomplete.",
        reviewed_at="2026-04-15T05:41:56+00:00",
    )
    payload = reviewed_output.to_dict()
    payload["missing_elements"] = []

    errors = reviewed_output_contract_errors(payload)

    assert "missing_elements must mirror extracted_review_packet.missing_elements." in errors


def test_reviewed_output_contract_rejects_override_without_reviewer_note(
    sample_bundle_dir,
    load_sample_bundle,
) -> None:
    bundle = load_sample_bundle(sample_bundle_dir / "bundle_002_incomplete.json")
    packet = build_review_packet(parse_bundle(bundle))
    reviewed_output = build_reviewed_output(
        packet,
        HumanReviewDecision.CONFIRM_READY,
        reviewer_note="Reviewer accepted the packet despite initial gaps.",
        reviewed_at="2026-04-15T05:41:56+00:00",
    )
    payload = reviewed_output.to_dict()
    payload["reviewer_note"] = ""

    errors = reviewed_output_contract_errors(payload)

    assert (
        "reviewer_note is required when human_review_decision overrides "
        "status_before_review."
    ) in errors


def test_checked_in_outputs_follow_reviewed_output_contract() -> None:
    output_paths = sorted(Path("outputs").glob("*.json"))

    assert output_paths
    for output_path in output_paths:
        payload = load_json_file(output_path)
        errors = reviewed_output_contract_errors(payload)
        assert errors == [], f"{output_path}: {errors}"
