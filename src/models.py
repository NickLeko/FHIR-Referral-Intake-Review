from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PacketStatus(str, Enum):
    REVIEW_READY = "REVIEW_READY"
    INCOMPLETE = "INCOMPLETE"
    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"


class HumanReviewDecision(str, Enum):
    CONFIRM_READY = "CONFIRM_READY"
    CONFIRM_INCOMPLETE = "CONFIRM_INCOMPLETE"
    ESCALATE_HUMAN_CONFIRMATION = "ESCALATE_HUMAN_CONFIRMATION"


@dataclass(frozen=True)
class TraceEntry:
    resource_type: str
    resource_id: str
    field_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "field_path": self.field_path,
        }


@dataclass
class ParsedBundle:
    bundle_id: str
    raw_bundle: dict[str, Any]
    resources_by_type: dict[str, list[dict[str, Any]]]
    resources_by_reference: dict[str, dict[str, Any]]
    unsupported_resources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ReviewPacket:
    intake_id: str
    bundle_id: str
    requested_service: str | None
    referral_reason: str | None
    ordering_provider: str | None
    patient_age_group: str | None
    encounter_context: str | None
    supporting_diagnosis: list[str] = field(default_factory=list)
    key_observations: list[str] = field(default_factory=list)
    referenced_documents: list[str] = field(default_factory=list)
    priority: str | None = None
    missing_elements: list[str] = field(default_factory=list)
    ambiguous_elements: list[str] = field(default_factory=list)
    fields_requiring_human_confirmation: list[str] = field(default_factory=list)
    unsupported_elements: list[str] = field(default_factory=list)
    source_trace: dict[str, list[TraceEntry]] = field(default_factory=dict)
    recommended_next_admin_action: str = ""
    status: PacketStatus = PacketStatus.INCOMPLETE

    def to_dict(self) -> dict[str, Any]:
        return {
            "intake_id": self.intake_id,
            "bundle_id": self.bundle_id,
            "requested_service": self.requested_service,
            "referral_reason": self.referral_reason,
            "ordering_provider": self.ordering_provider,
            "patient_age_group": self.patient_age_group,
            "encounter_context": self.encounter_context,
            "supporting_diagnosis": self.supporting_diagnosis,
            "key_observations": self.key_observations,
            "referenced_documents": self.referenced_documents,
            "priority": self.priority,
            "missing_elements": self.missing_elements,
            "ambiguous_elements": self.ambiguous_elements,
            "fields_requiring_human_confirmation": self.fields_requiring_human_confirmation,
            "unsupported_elements": self.unsupported_elements,
            "source_trace": {
                field_name: [entry.to_dict() for entry in entries]
                for field_name, entries in self.source_trace.items()
            },
            "recommended_next_admin_action": self.recommended_next_admin_action,
            "status": self.status.value,
        }


@dataclass
class ReviewedOutput:
    bundle_id: str
    extracted_review_packet: ReviewPacket
    status_before_review: PacketStatus
    human_review_decision: HumanReviewDecision
    reviewer_name: str
    reviewer_note: str
    reviewed_at: str
    final_status: PacketStatus
    final_reviewed_handoff_summary: str
    recommended_next_admin_step: str

    def to_dict(self) -> dict[str, Any]:
        packet_dict = self.extracted_review_packet.to_dict()
        return {
            "bundle_id": self.bundle_id,
            "extracted_review_packet": packet_dict,
            "status_before_review": self.status_before_review.value,
            "missing_elements": packet_dict["missing_elements"],
            "ambiguous_elements": packet_dict["ambiguous_elements"],
            "fields_requiring_human_confirmation": packet_dict[
                "fields_requiring_human_confirmation"
            ],
            "source_trace_map": packet_dict["source_trace"],
            "human_review_decision": self.human_review_decision.value,
            "reviewer_name": self.reviewer_name,
            "reviewer_note": self.reviewer_note,
            "reviewed_at": self.reviewed_at,
            "final_status": self.final_status.value,
            "final_reviewed_handoff_summary": self.final_reviewed_handoff_summary,
            "recommended_next_admin_step": self.recommended_next_admin_step,
        }
