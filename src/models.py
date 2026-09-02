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
class ResourceProvenance:
    server_base_url: str
    resource_type: str
    resource_id: str
    version_id: str | None
    last_updated: str | None
    fetched_at: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "server_base_url": self.server_base_url,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "version_id": self.version_id,
            "last_updated": self.last_updated,
            "fetched_at": self.fetched_at,
        }


@dataclass
class InputProvenance:
    source_type: str = "mock"
    resources: list[ResourceProvenance] = field(default_factory=list)
    scope_notes: list[str] = field(default_factory=list)

    @classmethod
    def mock(cls) -> InputProvenance:
        return cls(source_type="mock")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "resources": [resource.to_dict() for resource in self.resources],
            "scope_notes": self.scope_notes,
        }


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


@dataclass(frozen=True)
class IssueRationale:
    field: str
    issue_type: str
    rationale: str
    source: str = ""
    evidence: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "issue_type": self.issue_type,
            "rationale": self.rationale,
            "source": self.source,
            "evidence": self.evidence,
        }


@dataclass
class ParsedBundle:
    bundle_id: str
    raw_bundle: dict[str, Any]
    resources_by_type: dict[str, list[dict[str, Any]]]
    resources_by_reference: dict[str, dict[str, Any]]
    unsupported_resources: list[dict[str, str]] = field(default_factory=list)
    input_provenance: InputProvenance = field(default_factory=InputProvenance.mock)


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
    issue_rationales: list[IssueRationale] = field(default_factory=list)
    source_trace: dict[str, list[TraceEntry]] = field(default_factory=dict)
    recommended_next_admin_action: str = ""
    status: PacketStatus = PacketStatus.INCOMPLETE
    input_provenance: InputProvenance = field(default_factory=InputProvenance.mock)

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
            "issue_rationales": [issue.to_dict() for issue in self.issue_rationales],
            "source_trace": {
                field_name: [entry.to_dict() for entry in entries]
                for field_name, entries in self.source_trace.items()
            },
            "recommended_next_admin_action": self.recommended_next_admin_action,
            "status": self.status.value,
            "input_provenance": self.input_provenance.to_dict(),
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
            "issue_rationales": packet_dict["issue_rationales"],
            "source_trace_map": packet_dict["source_trace"],
            "human_review_decision": self.human_review_decision.value,
            "reviewer_name": self.reviewer_name,
            "reviewer_note": self.reviewer_note,
            "reviewed_at": self.reviewed_at,
            "final_status": self.final_status.value,
            "final_reviewed_handoff_summary": self.final_reviewed_handoff_summary,
            "recommended_next_admin_step": self.recommended_next_admin_step,
        }
