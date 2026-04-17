from __future__ import annotations

from src.mapping import build_review_packet
from src.parser import parse_bundle
from src.review import HumanReviewDecision, build_reviewed_output
from src.utils import list_sample_bundle_paths, load_json_file, sample_output_path, save_json_file

SAMPLE_REVIEWED_AT = "2026-04-15T05:41:56+00:00"

PRESET_DECISIONS = {
    "bundle_001_review_ready.json": (
        HumanReviewDecision.CONFIRM_READY,
        "Packet is sufficiently complete for downstream administrative handling.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_002_incomplete.json": (
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        "Ordering provider, encounter context, and diagnosis support are still missing.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_003_human_confirmation.json": (
        HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION,
        "Requested specialty and ordering provider identity need clarification before routing.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_004_missing_requester.json": (
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        "Ordering provider is missing even though the clinical and encounter context is present.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_005_unresolved_diagnosis_reference.json": (
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        "The referenced diagnosis could not be resolved, so diagnosis support is incomplete.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_006_ambiguous_payer_context.json": (
        HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION,
        "Coverage context is present but outside the supported parser subset and requires review.",
        SAMPLE_REVIEWED_AT,
    ),
    "bundle_007_incomplete_patient_demographics.json": (
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        "Patient age group cannot be derived because birth date is missing.",
        SAMPLE_REVIEWED_AT,
    ),
}


def main() -> None:
    for bundle_path in list_sample_bundle_paths():
        bundle_payload = load_json_file(bundle_path)
        parsed_bundle = parse_bundle(bundle_payload)
        packet = build_review_packet(parsed_bundle)
        decision, reviewer_note, reviewed_at = PRESET_DECISIONS[bundle_path.name]
        reviewed_output = build_reviewed_output(
            packet,
            decision,
            reviewer_note=reviewer_note,
            reviewed_at=reviewed_at,
        )
        output_path = sample_output_path(bundle_path)
        save_json_file(output_path, reviewed_output.to_dict())
        print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
