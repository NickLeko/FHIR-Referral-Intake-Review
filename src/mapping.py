from __future__ import annotations

from typing import Any

from src.models import IssueRationale, ParsedBundle, ReviewPacket
from src.parser import get_first_resource, get_resources, resolve_reference
from src.review import classify_status, recommended_next_admin_action_for_status
from src.tracing import add_trace, make_trace
from src.utils import (
    age_group_from_birth_date,
    clean_text,
    extract_codeable_concept_text,
    extract_human_name,
    join_unique,
    summarize_condition,
    summarize_observation_value,
)

GENERIC_SERVICE_TERMS = {
    "consult",
    "evaluation",
    "evaluate and treat",
    "specialty consult",
    "service request",
}
AMBIGUOUS_REASON_MARKERS = (" vs ", "possible", "unclear", "rule out", "/")
MISSING_FIELD_RATIONALES = {
    "requested_service": (
        "ServiceRequest did not include a usable service description for routing.",
        "ServiceRequest.code",
    ),
    "referral_reason": (
        "No usable referral reason or referenced diagnosis was available for intake review.",
        "ServiceRequest.reasonCode / ServiceRequest.reasonReference",
    ),
    "ordering_provider": (
        "No requester reference or display value was available to identify the ordering provider.",
        "ServiceRequest.requester",
    ),
    "patient_age_group": (
        "Patient birth date was missing or unusable, so age group could not be derived.",
        "Patient.birthDate",
    ),
    "encounter_context": (
        "No encounter context could be resolved for scheduling or authorization handoff.",
        "ServiceRequest.encounter / Encounter",
    ),
    "supporting_diagnosis": (
        "No supporting diagnosis could be summarized from referenced or bundled Condition resources.",
        "Condition.code",
    ),
}
AMBIGUOUS_FIELD_RATIONALES = {
    "requested_service": (
        "Requested service is too generic to choose a reliable specialty route.",
        "ServiceRequest.code",
    ),
    "referral_reason": (
        "Referral reason contains ambiguity markers that require human clarification.",
        "ServiceRequest.reasonCode",
    ),
    "ordering_provider": (
        "Requester display was present without a resolvable Practitioner reference.",
        "ServiceRequest.requester",
    ),
    "supporting_diagnosis": (
        "One or more diagnosis references could not be resolved to supported Condition resources.",
        "ServiceRequest.reasonReference",
    ),
}


def build_review_packet(parsed_bundle: ParsedBundle) -> ReviewPacket:
    trace_map: dict[str, list] = {}

    service_request = get_first_resource(parsed_bundle, "ServiceRequest")
    patient = _resolve_patient(parsed_bundle, service_request)
    encounter = _resolve_encounter(parsed_bundle, service_request)

    requested_service = _extract_requested_service(service_request, trace_map)
    referral_reason = _extract_referral_reason(service_request, parsed_bundle, trace_map)
    ordering_provider = _extract_ordering_provider(service_request, parsed_bundle, trace_map)
    patient_age_group = _extract_patient_age_group(patient, trace_map)
    encounter_context = _extract_encounter_context(encounter, trace_map)
    supporting_diagnosis = _extract_supporting_diagnosis(
        service_request, parsed_bundle, trace_map
    )
    key_observations = _extract_observations(service_request, parsed_bundle, trace_map)
    referenced_documents = _extract_documents(service_request, parsed_bundle, trace_map)
    priority = _extract_priority(service_request, trace_map)

    packet = ReviewPacket(
        intake_id=parsed_bundle.bundle_id,
        bundle_id=parsed_bundle.bundle_id,
        requested_service=requested_service,
        referral_reason=referral_reason,
        ordering_provider=ordering_provider,
        patient_age_group=patient_age_group,
        encounter_context=encounter_context,
        supporting_diagnosis=supporting_diagnosis,
        key_observations=key_observations,
        referenced_documents=referenced_documents,
        priority=priority,
        source_trace=trace_map,
    )

    packet.missing_elements = _detect_missing_elements(packet)
    packet.ambiguous_elements = _detect_ambiguous_elements(
        packet,
        service_request,
        parsed_bundle,
    )
    packet.fields_requiring_human_confirmation = join_unique(packet.ambiguous_elements)
    packet.unsupported_elements = [
        f"{item['resource_type']}/{item['resource_id']}"
        for item in parsed_bundle.unsupported_resources
    ]
    packet.issue_rationales = _build_issue_rationales(
        packet,
        parsed_bundle,
        service_request,
    )
    packet.status = classify_status(
        packet.missing_elements,
        packet.fields_requiring_human_confirmation,
        packet.unsupported_elements,
    )
    packet.recommended_next_admin_action = recommended_next_admin_action_for_status(
        packet.status
    )
    return packet


def _resolve_patient(
    parsed_bundle: ParsedBundle,
    service_request: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if service_request is None:
        return None

    subject_ref = service_request.get("subject")
    if not isinstance(subject_ref, dict):
        return None

    resolved = resolve_reference(parsed_bundle, clean_text(subject_ref.get("reference")))
    if resolved and resolved.get("resourceType") == "Patient":
        return resolved
    return None


def _resolve_encounter(
    parsed_bundle: ParsedBundle,
    service_request: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if service_request is None:
        return None

    encounter_ref = service_request.get("encounter")
    if isinstance(encounter_ref, dict):
        resolved = resolve_reference(parsed_bundle, clean_text(encounter_ref.get("reference")))
        if resolved:
            return resolved

    encounters = get_resources(parsed_bundle, "Encounter")
    if len(encounters) == 1:
        return encounters[0]
    return None


def _extract_requested_service(
    service_request: dict[str, Any] | None,
    trace_map: dict[str, list],
) -> str | None:
    if service_request is None:
        return None

    code = service_request.get("code")
    value = extract_codeable_concept_text(code)
    if not value or not isinstance(code, dict):
        return value

    if clean_text(code.get("text")):
        add_trace(trace_map, "requested_service", make_trace(service_request, "code.text"))
    coding = code.get("coding")
    if isinstance(coding, list) and coding:
        add_trace(
            trace_map,
            "requested_service",
            make_trace(service_request, "code.coding[0].display"),
        )
    return value


def _extract_referral_reason(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
) -> str | None:
    if service_request is None:
        return None

    reason_values: list[str] = []
    reason_codes = service_request.get("reasonCode")
    if isinstance(reason_codes, list):
        for index, item in enumerate(reason_codes):
            if not isinstance(item, dict):
                continue
            text = extract_codeable_concept_text(item)
            if text:
                reason_values.append(text)
                if clean_text(item.get("text")):
                    add_trace(
                        trace_map,
                        "referral_reason",
                        make_trace(service_request, f"reasonCode[{index}].text"),
                    )
                if isinstance(item.get("coding"), list) and item["coding"]:
                    add_trace(
                        trace_map,
                        "referral_reason",
                        make_trace(
                            service_request,
                            f"reasonCode[{index}].coding[0].display",
                        ),
                    )

    if reason_values:
        return "; ".join(join_unique(reason_values))

    diagnoses = _collect_referenced_conditions(service_request, parsed_bundle)
    summaries = [summary for condition in diagnoses if (summary := summarize_condition(condition))]
    if summaries:
        _trace_resolved_reason_references(
            service_request,
            parsed_bundle,
            trace_map,
            "referral_reason",
        )
        for condition in diagnoses:
            add_trace(trace_map, "referral_reason", make_trace(condition, "code"))
        return "; ".join(join_unique(summaries))
    return None


def _extract_ordering_provider(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
) -> str | None:
    if service_request is None:
        return None

    requester = service_request.get("requester")
    if not isinstance(requester, dict):
        return None

    requester_reference = clean_text(requester.get("reference"))
    requester_display = clean_text(requester.get("display"))
    if requester_reference:
        add_trace(
            trace_map,
            "ordering_provider",
            make_trace(service_request, "requester.reference"),
        )
        practitioner = resolve_reference(parsed_bundle, requester_reference)
        if practitioner:
            names = practitioner.get("name")
            if isinstance(names, list) and names:
                resolved_name = extract_human_name(names[0])
                if resolved_name:
                    add_trace(
                        trace_map,
                        "ordering_provider",
                        make_trace(practitioner, "name[0]"),
                    )
                    return resolved_name
    if requester_display:
        add_trace(
            trace_map,
            "ordering_provider",
            make_trace(service_request, "requester.display"),
        )
        return requester_display
    return None


def _extract_patient_age_group(
    patient: dict[str, Any] | None,
    trace_map: dict[str, list],
) -> str | None:
    if patient is None:
        return None

    birth_date = clean_text(patient.get("birthDate"))
    value = age_group_from_birth_date(birth_date)
    if birth_date:
        add_trace(trace_map, "patient_age_group", make_trace(patient, "birthDate"))
    return value


def _extract_encounter_context(
    encounter: dict[str, Any] | None,
    trace_map: dict[str, list],
) -> str | None:
    if encounter is None:
        return None

    class_display = None
    encounter_class = encounter.get("class")
    if isinstance(encounter_class, dict):
        class_display = clean_text(encounter_class.get("display")) or clean_text(
            encounter_class.get("code")
        )
        if class_display:
            add_trace(trace_map, "encounter_context", make_trace(encounter, "class"))

    encounter_type = None
    types = encounter.get("type")
    if isinstance(types, list) and types:
        encounter_type = extract_codeable_concept_text(types[0])
        if encounter_type:
            add_trace(trace_map, "encounter_context", make_trace(encounter, "type[0]"))

    period_start = None
    period = encounter.get("period")
    if isinstance(period, dict):
        period_start = clean_text(period.get("start"))
        if period_start:
            add_trace(trace_map, "encounter_context", make_trace(encounter, "period.start"))

    context_parts = [part for part in [class_display, encounter_type, period_start] if part]
    return " | ".join(context_parts) if context_parts else None


def _extract_supporting_diagnosis(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
) -> list[str]:
    if service_request is None:
        return []

    conditions = _collect_referenced_conditions(service_request, parsed_bundle)
    if not conditions and not _has_reason_references(service_request):
        conditions = get_resources(parsed_bundle, "Condition")
    elif conditions:
        _trace_resolved_reason_references(
            service_request,
            parsed_bundle,
            trace_map,
            "supporting_diagnosis",
        )

    diagnosis_summaries: list[str] = []
    for index, condition in enumerate(conditions):
        summary = summarize_condition(condition)
        if not summary:
            continue
        diagnosis_summaries.append(summary)
        add_trace(
            trace_map,
            "supporting_diagnosis",
            make_trace(condition, "code"),
        )
        if index == 0 and clean_text(condition.get("clinicalStatus")):
            add_trace(
                trace_map,
                "supporting_diagnosis",
                make_trace(condition, "clinicalStatus"),
            )
    return join_unique(diagnosis_summaries)


def _extract_observations(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
) -> list[str]:
    observations = _collect_supporting_info(service_request, parsed_bundle, "Observation")
    if not observations:
        observations = get_resources(parsed_bundle, "Observation")

    summaries: list[str] = []
    for observation in observations:
        code_text = extract_codeable_concept_text(observation.get("code")) or "Observation"
        value_text = summarize_observation_value(observation)
        if value_text:
            summaries.append(f"{code_text}: {value_text}")
        else:
            summaries.append(code_text)
        add_trace(trace_map, "key_observations", make_trace(observation, "code"))
        if observation.get("valueQuantity") is not None:
            add_trace(trace_map, "key_observations", make_trace(observation, "valueQuantity"))
        elif observation.get("valueString") is not None:
            add_trace(trace_map, "key_observations", make_trace(observation, "valueString"))
    return join_unique(summaries)


def _extract_documents(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
) -> list[str]:
    documents = _collect_supporting_info(service_request, parsed_bundle, "DocumentReference")
    if not documents:
        documents = get_resources(parsed_bundle, "DocumentReference")

    summaries: list[str] = []
    for document in documents:
        description = clean_text(document.get("description"))
        type_text = extract_codeable_concept_text(document.get("type"))
        content = document.get("content")
        attachment_title = None
        if isinstance(content, list) and content:
            attachment = content[0].get("attachment")
            if isinstance(attachment, dict):
                attachment_title = clean_text(attachment.get("title"))
        summary = description or type_text or attachment_title
        if not summary:
            continue
        summaries.append(summary)
        if description:
            add_trace(trace_map, "referenced_documents", make_trace(document, "description"))
        elif type_text:
            add_trace(trace_map, "referenced_documents", make_trace(document, "type"))
        elif attachment_title:
            add_trace(
                trace_map,
                "referenced_documents",
                make_trace(document, "content[0].attachment.title"),
            )
    return join_unique(summaries)


def _extract_priority(
    service_request: dict[str, Any] | None,
    trace_map: dict[str, list],
) -> str | None:
    if service_request is None:
        return None

    priority = clean_text(service_request.get("priority"))
    if priority:
        add_trace(trace_map, "priority", make_trace(service_request, "priority"))
    return priority


def _collect_referenced_conditions(
    service_request: dict[str, Any],
    parsed_bundle: ParsedBundle,
) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    reason_references = service_request.get("reasonReference")
    if not isinstance(reason_references, list):
        return conditions

    for item in reason_references:
        if not isinstance(item, dict):
            continue
        reference = clean_text(item.get("reference"))
        resource = resolve_reference(parsed_bundle, reference)
        if resource and resource.get("resourceType") == "Condition":
            conditions.append(resource)
    return conditions


def _has_reason_references(service_request: dict[str, Any] | None) -> bool:
    if service_request is None:
        return False
    reason_references = service_request.get("reasonReference")
    return isinstance(reason_references, list) and any(
        isinstance(item, dict) and clean_text(item.get("reference"))
        for item in reason_references
    )


def _unresolved_reason_reference_labels(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
) -> list[str]:
    if service_request is None:
        return []

    reason_references = service_request.get("reasonReference")
    if not isinstance(reason_references, list):
        return []

    unresolved: list[str] = []
    for item in reason_references:
        if not isinstance(item, dict):
            continue
        reference = clean_text(item.get("reference"))
        if not reference:
            continue
        resource = resolve_reference(parsed_bundle, reference)
        if resource is None or resource.get("resourceType") != "Condition":
            unresolved.append(reference)
    return join_unique(unresolved)


def _trace_resolved_reason_references(
    service_request: dict[str, Any],
    parsed_bundle: ParsedBundle,
    trace_map: dict[str, list],
    field_name: str,
) -> None:
    reason_references = service_request.get("reasonReference")
    if not isinstance(reason_references, list):
        return

    for index, item in enumerate(reason_references):
        if not isinstance(item, dict):
            continue
        reference = clean_text(item.get("reference"))
        resource = resolve_reference(parsed_bundle, reference)
        if resource and resource.get("resourceType") == "Condition":
            add_trace(
                trace_map,
                field_name,
                make_trace(service_request, f"reasonReference[{index}].reference"),
            )


def _collect_supporting_info(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
    resource_type: str,
) -> list[dict[str, Any]]:
    if service_request is None:
        return []

    supporting_info = service_request.get("supportingInfo")
    if not isinstance(supporting_info, list):
        return []

    resources: list[dict[str, Any]] = []
    for item in supporting_info:
        if not isinstance(item, dict):
            continue
        reference = clean_text(item.get("reference"))
        resource = resolve_reference(parsed_bundle, reference)
        if resource and resource.get("resourceType") == resource_type:
            resources.append(resource)
    return resources


def _detect_missing_elements(packet: ReviewPacket) -> list[str]:
    missing: list[str] = []
    required_fields = {
        "requested_service": packet.requested_service,
        "referral_reason": packet.referral_reason,
        "ordering_provider": packet.ordering_provider,
        "patient_age_group": packet.patient_age_group,
        "encounter_context": packet.encounter_context,
        "supporting_diagnosis": packet.supporting_diagnosis,
    }
    for field_name, value in required_fields.items():
        if value is None:
            missing.append(field_name)
        elif isinstance(value, list) and not value:
            missing.append(field_name)
    return missing


def _build_issue_rationales(
    packet: ReviewPacket,
    parsed_bundle: ParsedBundle,
    service_request: dict[str, Any] | None,
) -> list[IssueRationale]:
    issue_rationales: list[IssueRationale] = []
    unresolved_reason_references = _unresolved_reason_reference_labels(
        service_request,
        parsed_bundle,
    )

    for field_name in packet.missing_elements:
        rationale, source = MISSING_FIELD_RATIONALES.get(
            field_name,
            ("Required intake field was not available.", ""),
        )
        issue_rationales.append(
            IssueRationale(
                field=field_name,
                issue_type="missing",
                rationale=rationale,
                source=_source_for_issue(
                    packet,
                    field_name,
                    source,
                    unresolved_reason_references,
                ),
                evidence=_evidence_for_issue(
                    packet,
                    field_name,
                    unresolved_reason_references,
                ),
            )
        )

    for field_name in packet.ambiguous_elements:
        rationale, source = AMBIGUOUS_FIELD_RATIONALES.get(
            field_name,
            ("Extracted value requires human confirmation before routing.", ""),
        )
        issue_rationales.append(
            IssueRationale(
                field=field_name,
                issue_type="ambiguous",
                rationale=rationale,
                source=_source_for_issue(
                    packet,
                    field_name,
                    source,
                    unresolved_reason_references,
                ),
                evidence=_evidence_for_issue(
                    packet,
                    field_name,
                    unresolved_reason_references,
                ),
            )
        )

    for item in parsed_bundle.unsupported_resources:
        resource_label = f"{item['resource_type']}/{item['resource_id']}"
        issue_rationales.append(
            IssueRationale(
                field=resource_label,
                issue_type="unsupported",
                rationale=(
                    "Bundle contains a resource outside the supported parser subset; "
                    "reviewer should inspect it before treating the handoff as complete."
                ),
                source=resource_label,
                evidence="Unsupported resource was present in the submitted bundle.",
            )
        )

    return issue_rationales


def _source_for_field(packet: ReviewPacket, field_name: str) -> str:
    trace_entries = packet.source_trace.get(field_name, [])
    return "; ".join(
        f"{entry.resource_type}/{entry.resource_id}.{entry.field_path}"
        for entry in trace_entries
    )


def _source_for_issue(
    packet: ReviewPacket,
    field_name: str,
    fallback_source: str,
    unresolved_reason_references: list[str],
) -> str:
    if field_name == "supporting_diagnosis" and unresolved_reason_references:
        return "ServiceRequest.reasonReference"
    return _source_for_field(packet, field_name) or fallback_source


def _evidence_for_issue(
    packet: ReviewPacket,
    field_name: str,
    unresolved_reason_references: list[str],
) -> str:
    if field_name == "supporting_diagnosis" and unresolved_reason_references:
        return f"Unresolved references: {', '.join(unresolved_reason_references)}"

    value = getattr(packet, field_name, None)
    if isinstance(value, list):
        return "; ".join(value) if value else "No value extracted."
    if value is None:
        return "No value extracted."
    return str(value)


def _detect_ambiguous_elements(
    packet: ReviewPacket,
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
) -> list[str]:
    ambiguous: list[str] = []

    requested_service = (packet.requested_service or "").lower()
    if requested_service in GENERIC_SERVICE_TERMS:
        ambiguous.append("requested_service")

    referral_reason = (packet.referral_reason or "").lower()
    if any(marker in referral_reason for marker in AMBIGUOUS_REASON_MARKERS):
        ambiguous.append("referral_reason")

    if _provider_display_without_resolved_practitioner(service_request, parsed_bundle):
        ambiguous.append("ordering_provider")

    if packet.supporting_diagnosis and _unresolved_reason_reference_labels(
        service_request,
        parsed_bundle,
    ):
        ambiguous.append("supporting_diagnosis")

    return join_unique(ambiguous)


def _provider_display_without_resolved_practitioner(
    service_request: dict[str, Any] | None,
    parsed_bundle: ParsedBundle,
) -> bool:
    if service_request is None:
        return False

    requester = service_request.get("requester")
    if not isinstance(requester, dict):
        return False

    requester_display = clean_text(requester.get("display"))
    requester_reference = clean_text(requester.get("reference"))
    if requester_display and not requester_reference:
        return True
    if requester_display and requester_reference:
        return resolve_reference(parsed_bundle, requester_reference) is None
    return False
