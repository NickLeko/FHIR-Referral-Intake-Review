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
    reviewer_name: str = "Administrative Reviewer",
    reviewed_at: str | None = None,
) -> ReviewedOutput:
    reviewer_note = reviewer_note.strip()
    if decision_overrides_status(packet.status, decision) and not reviewer_note:
        raise ValueError("Reviewer note is required when overriding the initial status.")

    final_status = decision_to_status(decision)
    next_step = recommended_next_admin_action_for_status(final_status)
    summary = (
        f"Referral intake {packet.bundle_id} was reviewed as {final_status.value}. "
        f"Requested service: {packet.requested_service or 'Unavailable'}. "
        f"Ordering provider: {packet.ordering_provider or 'Unavailable'}. "
        f"Missing elements: {', '.join(packet.missing_elements) or 'none'}. "
        f"Ambiguous elements: {', '.join(packet.ambiguous_elements) or 'none'}. "
        f"Reviewer note: {reviewer_note or 'None provided'}. "
        f"Next admin step: {next_step}"
    )
    return ReviewedOutput(
        bundle_id=packet.bundle_id,
        extracted_review_packet=packet,
        status_before_review=packet.status,
        human_review_decision=decision,
        reviewer_name=reviewer_name,
        reviewer_note=reviewer_note,
        reviewed_at=reviewed_at or now_iso(),
        final_status=final_status,
        final_reviewed_handoff_summary=summary,
        recommended_next_admin_step=next_step,
    )
