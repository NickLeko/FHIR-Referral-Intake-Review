from __future__ import annotations

from src.models import HumanReviewDecision, PacketStatus, ReviewPacket, ReviewedOutput
from src.utils import now_iso


def classify_status(
    missing_elements: list[str],
    fields_requiring_human_confirmation: list[str],
    unsupported_elements: list[str],
) -> PacketStatus:
    if missing_elements:
        return PacketStatus.INCOMPLETE
    if fields_requiring_human_confirmation or unsupported_elements:
        return PacketStatus.HUMAN_CONFIRMATION_REQUIRED
    return PacketStatus.REVIEW_READY


def recommended_next_admin_action_for_status(status: PacketStatus) -> str:
    if status == PacketStatus.REVIEW_READY:
        return "Proceed to downstream administrative handling after reviewer confirmation."
    if status == PacketStatus.INCOMPLETE:
        return "Request the missing intake elements before downstream administrative work."
    return "Route for manual clarification before downstream scheduling or authorization tasks."


def default_decision_for_status(status: PacketStatus) -> HumanReviewDecision:
    if status == PacketStatus.REVIEW_READY:
        return HumanReviewDecision.CONFIRM_READY
    if status == PacketStatus.INCOMPLETE:
        return HumanReviewDecision.CONFIRM_INCOMPLETE
    return HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION


def decision_to_status(decision: HumanReviewDecision) -> PacketStatus:
    if decision == HumanReviewDecision.CONFIRM_READY:
        return PacketStatus.REVIEW_READY
    if decision == HumanReviewDecision.CONFIRM_INCOMPLETE:
        return PacketStatus.INCOMPLETE
    return PacketStatus.HUMAN_CONFIRMATION_REQUIRED


def decision_overrides_status(
    current_status: PacketStatus,
    decision: HumanReviewDecision,
) -> bool:
    return decision_to_status(decision) != current_status


def build_reviewed_output(
    packet: ReviewPacket,
    decision: HumanReviewDecision,
    reviewer_note: str = "",
    reviewer_name: str = "Referral Intake Coordinator",
    reviewed_at: str | None = None,
) -> ReviewedOutput:
    reviewer_note = reviewer_note.strip()
    if decision_overrides_status(packet.status, decision) and not reviewer_note:
        raise ValueError("Reviewer note is required when overriding the initial status.")

    reviewed_at = reviewed_at or now_iso()
    final_status = decision_to_status(decision)
    next_step = recommended_next_admin_action_for_status(final_status)
    summary = _build_final_handoff_summary(
        packet=packet,
        decision=decision,
        final_status=final_status,
        reviewer_name=reviewer_name,
        reviewer_note=reviewer_note,
        reviewed_at=reviewed_at,
        next_step=next_step,
    )
    return ReviewedOutput(
        bundle_id=packet.bundle_id,
        extracted_review_packet=packet,
        status_before_review=packet.status,
        human_review_decision=decision,
        reviewer_name=reviewer_name,
        reviewer_note=reviewer_note,
        reviewed_at=reviewed_at,
        final_status=final_status,
        final_reviewed_handoff_summary=summary,
        recommended_next_admin_step=next_step,
    )


def _build_final_handoff_summary(
    packet: ReviewPacket,
    decision: HumanReviewDecision,
    final_status: PacketStatus,
    reviewer_name: str,
    reviewer_note: str,
    reviewed_at: str,
    next_step: str,
) -> str:
    known_facts = _known_fact_summary(packet)
    blockers = _blocker_summary(packet)
    reviewer_note_text = reviewer_note or "No additional reviewer note provided."
    return "\n".join(
        [
            f"Service: {packet.requested_service or 'Unavailable'} | Priority: {packet.priority or 'not stated'}",
            f"Known facts: {known_facts}",
            f"Blockers: {blockers}",
            (
                "Review: initial "
                f"{packet.status.value} -> final {final_status.value} via {decision.value}"
            ),
            f"Reviewer: {reviewer_name} | {reviewed_at}",
            f"Reviewer note: {reviewer_note_text}",
            f"Next step: {next_step}",
        ]
    )


def _known_fact_summary(packet: ReviewPacket) -> str:
    facts = [
        ("ordering provider", packet.ordering_provider),
        ("patient age group", packet.patient_age_group),
        ("encounter", packet.encounter_context),
        (
            "supporting diagnosis",
            "; ".join(packet.supporting_diagnosis) if packet.supporting_diagnosis else None,
        ),
        (
            "key observations",
            "; ".join(packet.key_observations) if packet.key_observations else None,
        ),
        (
            "documents",
            "; ".join(packet.referenced_documents) if packet.referenced_documents else None,
        ),
    ]
    populated_facts = [f"{label} {value}" for label, value in facts if value]
    return "; ".join(populated_facts) if populated_facts else "No extracted supporting facts."


def _blocker_summary(packet: ReviewPacket) -> str:
    blocker_groups = []
    if packet.missing_elements:
        blocker_groups.append(f"missing {', '.join(packet.missing_elements)}")
    if packet.ambiguous_elements:
        blocker_groups.append(f"ambiguous {', '.join(packet.ambiguous_elements)}")
    if packet.unsupported_elements:
        blocker_groups.append(f"unsupported {', '.join(packet.unsupported_elements)}")
    return "; ".join(blocker_groups) if blocker_groups else "none"
