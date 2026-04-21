from __future__ import annotations

from dataclasses import dataclass

from src.mapping import build_review_packet
from src.parser import parse_bundle
from src.review import HumanReviewDecision, build_reviewed_output
from src.utils import list_sample_bundle_paths, load_json_file, sample_output_path, save_json_file

SAMPLE_REVIEWED_AT = "2026-04-15T05:41:56+00:00"
OVERRIDE_SAMPLE_REVIEWED_AT = "2026-04-15T06:12:09+00:00"
SAMPLE_REVIEWER_NAME = "Casey Nguyen, Referral Intake Coordinator"


@dataclass(frozen=True)
class SampleReviewSpec:
    decision: HumanReviewDecision
    reviewer_note: str
    reviewed_at: str
    artifact_label: str | None = None
    reviewer_name: str = SAMPLE_REVIEWER_NAME

PRESET_REVIEWS = {
    "bundle_001_review_ready.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_READY,
            reviewer_note="Packet is sufficiently complete for downstream administrative handling.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
    "bundle_002_incomplete.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_INCOMPLETE,
            reviewer_note="Ordering provider, encounter context, and diagnosis support are still missing.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
    "bundle_003_human_confirmation.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION,
            reviewer_note="Requested specialty and ordering provider identity need clarification before routing.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
    "bundle_004_missing_requester.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_INCOMPLETE,
            reviewer_note="Ordering provider is missing even though the clinical and encounter context is present.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
    "bundle_005_unresolved_diagnosis_reference.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_INCOMPLETE,
            reviewer_note="The referenced diagnosis could not be resolved, so diagnosis support is incomplete.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
    "bundle_006_ambiguous_payer_context.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION,
            reviewer_note="Coverage context is present but outside the supported parser subset and requires review.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        ),
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_READY,
            reviewer_note=(
                "Coverage details were manually reviewed from the bundled payer context and do not block downstream GI scheduling."
            ),
            reviewed_at=OVERRIDE_SAMPLE_REVIEWED_AT,
            artifact_label="override_ready",
        ),
    ],
    "bundle_007_incomplete_patient_demographics.json": [
        SampleReviewSpec(
            decision=HumanReviewDecision.CONFIRM_INCOMPLETE,
            reviewer_note="Patient age group cannot be derived because birth date is missing.",
            reviewed_at=SAMPLE_REVIEWED_AT,
        )
    ],
}


def main() -> None:
    for bundle_path in list_sample_bundle_paths():
        bundle_payload = load_json_file(bundle_path)
        parsed_bundle = parse_bundle(bundle_payload)
        packet = build_review_packet(parsed_bundle)
        for review_spec in PRESET_REVIEWS[bundle_path.name]:
            reviewed_output = build_reviewed_output(
                packet,
                review_spec.decision,
                reviewer_note=review_spec.reviewer_note,
                reviewer_name=review_spec.reviewer_name,
                reviewed_at=review_spec.reviewed_at,
            )
            output_path = sample_output_path(
                bundle_path,
                artifact_label=review_spec.artifact_label,
            )
            save_json_file(output_path, reviewed_output.to_dict())
            print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
