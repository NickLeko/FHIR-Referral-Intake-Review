from __future__ import annotations

from typing import Any

from src.models import HumanReviewDecision, PacketStatus

REVIEW_PACKET_CONTRACT_KEYS = (
    "intake_id",
    "bundle_id",
    "requested_service",
    "referral_reason",
    "ordering_provider",
    "patient_age_group",
    "encounter_context",
    "supporting_diagnosis",
    "key_observations",
    "referenced_documents",
    "priority",
    "missing_elements",
    "ambiguous_elements",
    "fields_requiring_human_confirmation",
    "unsupported_elements",
    "issue_rationales",
    "source_trace",
    "recommended_next_admin_action",
    "status",
    "input_provenance",
)

REVIEWED_OUTPUT_CONTRACT_KEYS = (
    "bundle_id",
    "extracted_review_packet",
    "status_before_review",
    "missing_elements",
    "ambiguous_elements",
    "fields_requiring_human_confirmation",
    "issue_rationales",
    "source_trace_map",
    "human_review_decision",
    "reviewer_name",
    "reviewer_note",
    "reviewed_at",
    "final_status",
    "final_reviewed_handoff_summary",
    "recommended_next_admin_step",
)

ISSUE_RATIONALE_CONTRACT_KEYS = (
    "field",
    "issue_type",
    "rationale",
    "source",
    "evidence",
)

TRACE_ENTRY_CONTRACT_KEYS = (
    "resource_type",
    "resource_id",
    "field_path",
)

INPUT_PROVENANCE_CONTRACT_KEYS = (
    "source_type",
    "resources",
    "scope_notes",
)

RESOURCE_PROVENANCE_CONTRACT_KEYS = (
    "server_base_url",
    "resource_type",
    "resource_id",
    "version_id",
    "last_updated",
    "fetched_at",
)

_STATUS_VALUES = {status.value for status in PacketStatus}
_SOURCE_TYPE_VALUES = {"mock", "live"}
_DECISION_VALUES = {decision.value for decision in HumanReviewDecision}
_FINAL_STATUS_BY_DECISION = {
    HumanReviewDecision.CONFIRM_READY.value: PacketStatus.REVIEW_READY.value,
    HumanReviewDecision.CONFIRM_INCOMPLETE.value: PacketStatus.INCOMPLETE.value,
    HumanReviewDecision.ESCALATE_HUMAN_CONFIRMATION.value: (
        PacketStatus.HUMAN_CONFIRMATION_REQUIRED.value
    ),
}


def reviewed_output_contract_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _check_exact_keys("reviewed_output", payload, REVIEWED_OUTPUT_CONTRACT_KEYS, errors)

    packet = payload.get("extracted_review_packet")
    if not isinstance(packet, dict):
        errors.append("extracted_review_packet must be an object.")
        return errors

    _check_exact_keys(
        "extracted_review_packet",
        packet,
        REVIEW_PACKET_CONTRACT_KEYS,
        errors,
        optional_keys=("input_provenance",),
    )
    _check_packet_contract(packet, errors)
    _check_reviewed_output_contract(payload, packet, errors)
    return errors


def _check_packet_contract(packet: dict[str, Any], errors: list[str]) -> None:
    for field_name in (
        "intake_id",
        "bundle_id",
        "recommended_next_admin_action",
        "status",
    ):
        _check_string(f"extracted_review_packet.{field_name}", packet.get(field_name), errors)

    for field_name in (
        "requested_service",
        "referral_reason",
        "ordering_provider",
        "patient_age_group",
        "encounter_context",
        "priority",
    ):
        _check_optional_string(
            f"extracted_review_packet.{field_name}",
            packet.get(field_name),
            errors,
        )

    for field_name in (
        "supporting_diagnosis",
        "key_observations",
        "referenced_documents",
        "missing_elements",
        "ambiguous_elements",
        "fields_requiring_human_confirmation",
        "unsupported_elements",
    ):
        _check_string_list(
            f"extracted_review_packet.{field_name}",
            packet.get(field_name),
            errors,
        )

    if packet.get("status") not in _STATUS_VALUES:
        errors.append("extracted_review_packet.status must be a known PacketStatus value.")

    _check_issue_rationales(
        "extracted_review_packet.issue_rationales",
        packet.get("issue_rationales"),
        errors,
    )
    _check_source_trace(
        "extracted_review_packet.source_trace",
        packet.get("source_trace"),
        errors,
    )
    if "input_provenance" in packet:
        _check_input_provenance(
            "extracted_review_packet.input_provenance",
            packet.get("input_provenance"),
            errors,
        )


def _check_reviewed_output_contract(
    payload: dict[str, Any],
    packet: dict[str, Any],
    errors: list[str],
) -> None:
    for field_name in (
        "bundle_id",
        "status_before_review",
        "human_review_decision",
        "reviewer_name",
        "reviewer_note",
        "reviewed_at",
        "final_status",
        "final_reviewed_handoff_summary",
        "recommended_next_admin_step",
    ):
        _check_string(field_name, payload.get(field_name), errors)

    for field_name in (
        "missing_elements",
        "ambiguous_elements",
        "fields_requiring_human_confirmation",
    ):
        _check_string_list(field_name, payload.get(field_name), errors)

    _check_issue_rationales("issue_rationales", payload.get("issue_rationales"), errors)
    _check_source_trace("source_trace_map", payload.get("source_trace_map"), errors)

    if payload.get("status_before_review") not in _STATUS_VALUES:
        errors.append("status_before_review must be a known PacketStatus value.")
    if payload.get("final_status") not in _STATUS_VALUES:
        errors.append("final_status must be a known PacketStatus value.")
    if payload.get("human_review_decision") not in _DECISION_VALUES:
        errors.append("human_review_decision must be a known HumanReviewDecision value.")

    if payload.get("bundle_id") != packet.get("bundle_id"):
        errors.append("bundle_id must match extracted_review_packet.bundle_id.")
    if payload.get("status_before_review") != packet.get("status"):
        errors.append("status_before_review must match extracted_review_packet.status.")

    for top_level_key, packet_key in (
        ("missing_elements", "missing_elements"),
        ("ambiguous_elements", "ambiguous_elements"),
        ("fields_requiring_human_confirmation", "fields_requiring_human_confirmation"),
        ("issue_rationales", "issue_rationales"),
        ("source_trace_map", "source_trace"),
    ):
        if payload.get(top_level_key) != packet.get(packet_key):
            errors.append(
                f"{top_level_key} must mirror extracted_review_packet.{packet_key}."
            )

    expected_final_status = _FINAL_STATUS_BY_DECISION.get(
        str(payload.get("human_review_decision"))
    )
    if expected_final_status and payload.get("final_status") != expected_final_status:
        errors.append("final_status must match human_review_decision.")
    if (
        expected_final_status
        and payload.get("status_before_review") != expected_final_status
        and (
            not isinstance(payload.get("reviewer_note"), str)
            or not payload["reviewer_note"].strip()
        )
    ):
        errors.append(
            "reviewer_note is required when human_review_decision overrides "
            "status_before_review."
        )


def _check_issue_rationales(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list.")
        return

    for index, item in enumerate(value):
        item_name = f"{name}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_name} must be an object.")
            continue
        _check_exact_keys(item_name, item, ISSUE_RATIONALE_CONTRACT_KEYS, errors)
        for field_name in ISSUE_RATIONALE_CONTRACT_KEYS:
            _check_string(f"{item_name}.{field_name}", item.get(field_name), errors)


def _check_source_trace(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object.")
        return

    for field_name, entries in value.items():
        if not isinstance(field_name, str):
            errors.append(f"{name} keys must be strings.")
            continue
        if not isinstance(entries, list):
            errors.append(f"{name}.{field_name} must be a list.")
            continue
        for index, item in enumerate(entries):
            item_name = f"{name}.{field_name}[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_name} must be an object.")
                continue
            _check_exact_keys(item_name, item, TRACE_ENTRY_CONTRACT_KEYS, errors)
            for trace_key in TRACE_ENTRY_CONTRACT_KEYS:
                _check_string(f"{item_name}.{trace_key}", item.get(trace_key), errors)


def _check_input_provenance(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object.")
        return

    _check_exact_keys(
        name,
        value,
        INPUT_PROVENANCE_CONTRACT_KEYS,
        errors,
        optional_keys=("scope_notes",),
    )
    _check_string(f"{name}.source_type", value.get("source_type"), errors)
    if value.get("source_type") not in _SOURCE_TYPE_VALUES:
        errors.append(f"{name}.source_type must be mock or live.")

    resources = value.get("resources")
    if not isinstance(resources, list):
        errors.append(f"{name}.resources must be a list.")
        return

    if "scope_notes" in value:
        _check_string_list(f"{name}.scope_notes", value.get("scope_notes"), errors)

    for index, resource in enumerate(resources):
        resource_name = f"{name}.resources[{index}]"
        if not isinstance(resource, dict):
            errors.append(f"{resource_name} must be an object.")
            continue
        _check_exact_keys(
            resource_name,
            resource,
            RESOURCE_PROVENANCE_CONTRACT_KEYS,
            errors,
        )
        for field_name in (
            "server_base_url",
            "resource_type",
            "resource_id",
            "fetched_at",
        ):
            _check_string(
                f"{resource_name}.{field_name}",
                resource.get(field_name),
                errors,
            )
        for field_name in ("version_id", "last_updated"):
            _check_optional_string(
                f"{resource_name}.{field_name}",
                resource.get(field_name),
                errors,
            )


def _check_exact_keys(
    name: str,
    value: dict[str, Any],
    expected_keys: tuple[str, ...],
    errors: list[str],
    optional_keys: tuple[str, ...] = (),
) -> None:
    expected = set(expected_keys)
    actual = set(value)
    missing = sorted(expected - actual - set(optional_keys))
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{name} is missing keys: {', '.join(missing)}.")
    if extra:
        errors.append(f"{name} has unexpected keys: {', '.join(extra)}.")


def _check_string(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{name} must be a string.")


def _check_optional_string(name: str, value: Any, errors: list[str]) -> None:
    if value is not None and not isinstance(value, str):
        errors.append(f"{name} must be a string or null.")


def _check_string_list(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list.")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{name}[{index}] must be a string.")
