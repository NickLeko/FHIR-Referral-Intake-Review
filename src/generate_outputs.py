from __future__ import annotations

from pathlib import Path

from src.mapping import build_review_packet
from src.parser import parse_bundle
from src.review import HumanReviewDecision, build_reviewed_output
from src.utils import list_sample_bundle_paths, load_json_file, sample_output_path, save_json_file

PRESET_DECISIONS = {
    "bundle_001_review_ready.json": (
        HumanReviewDecision.CONFIRM_READY,
        "Packet is sufficiently complete for downstream administrative handling.",
    ),
    "bundle_002_incomplete.json": (
        HumanReviewDecision.CONFIRM_INCOMPLETE,
        "Ordering provider, encounter context, and diagnosis support are still missing.",
    ),
    "bundle_003_human_confirmation.json": (
        HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION,
        "Requested specialty and ordering provider identity need clarification before routing.",
    ),
}


def main() -> None:
    for bundle_path in list_sample_bundle_paths():
        bundle_payload = load_json_file(bundle_path)
        parsed_bundle = parse_bundle(bundle_payload)
        packet = build_review_packet(parsed_bundle)
        decision, reviewer_note = PRESET_DECISIONS[bundle_path.name]
        reviewed_output = build_reviewed_output(packet, decision, reviewer_note=reviewer_note)
        output_path = sample_output_path(bundle_path)
        save_json_file(output_path, reviewed_output.to_dict())
        print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
