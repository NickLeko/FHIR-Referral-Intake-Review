from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.mapping import build_review_packet
from src.parser import BundleValidationError, parse_bundle
from src.review import (
    HumanReviewDecision,
    build_reviewed_output,
    default_decision_for_status,
    decision_overrides_status,
)
from src.utils import (
    list_sample_bundle_paths,
    load_json_file,
    review_history_output_path,
    save_json_file,
)


def packet_table_rows(packet_dict: dict[str, object]) -> list[dict[str, str]]:
    ordered_fields = [
        ("intake_id", "Intake ID"),
        ("bundle_id", "Bundle ID"),
        ("requested_service", "Requested service"),
        ("referral_reason", "Referral reason / indication"),
        ("ordering_provider", "Ordering provider"),
        ("patient_age_group", "Patient age group"),
        ("encounter_context", "Encounter context"),
        ("supporting_diagnosis", "Supporting diagnosis"),
        ("key_observations", "Key observations"),
        ("referenced_documents", "Referenced documents"),
        ("priority", "Priority / urgency"),
        ("recommended_next_admin_action", "Recommended next admin action"),
    ]
    rows: list[dict[str, str]] = []
    for key, label in ordered_fields:
        value = packet_dict.get(key)
        if isinstance(value, list):
            display_value = "\n".join(value) if value else "None"
        else:
            display_value = str(value or "None")
        rows.append({"Field": label, "Value": display_value})
    return rows


def trace_rows(source_trace: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for field_name, entries in source_trace.items():
        for entry in entries:
            rows.append(
                {
                    "Field": field_name,
                    "Resource Type": entry["resource_type"],
                    "Resource ID": entry["resource_id"],
                    "Field Path": entry["field_path"],
                }
            )
    return rows


def issue_table_rows(issue_rationales: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "Field": issue["field"],
            "Issue Type": issue["issue_type"],
            "Rationale": issue["rationale"],
            "Source": issue["source"] or "Not available",
            "Evidence": issue["evidence"] or "Not available",
        }
        for issue in issue_rationales
    ]


st.set_page_config(page_title="FHIR Referral Intake Review", layout="wide")

st.title("FHIR Referral Intake Review")
st.caption(
    "A small workflow prototype for transforming mock FHIR bundles into a "
    "human-reviewable referral intake packet with explicit HITL boundaries."
)

bundle_paths = list_sample_bundle_paths()
if not bundle_paths:
    st.error("No sample bundles were found in data/sample_bundles/.")
    st.stop()

bundle_lookup = {path.name: path for path in bundle_paths}
selected_bundle_name = st.selectbox("Select a mock FHIR bundle", options=list(bundle_lookup))
selected_bundle_path = bundle_lookup[selected_bundle_name]

try:
    bundle_payload = load_json_file(selected_bundle_path)
    parsed_bundle = parse_bundle(bundle_payload)
    packet = build_review_packet(parsed_bundle)
except BundleValidationError as error:
    st.error(f"Bundle validation failed: {error}")
    st.stop()

packet_dict = packet.to_dict()
status = packet_dict["status"]
st.info(f"Status before review: {status}")

left, right = st.columns([1.4, 1])

with left:
    st.subheader("Extracted Review Packet")
    st.table(packet_table_rows(packet_dict))

with right:
    st.subheader("Issues Requiring Attention")
    issue_rows = issue_table_rows(packet_dict["issue_rationales"])
    if issue_rows:
        st.dataframe(issue_rows, width="stretch", hide_index=True)
    else:
        st.success("No missing, ambiguous, or unsupported issues detected.")

st.subheader("Source Traceability")
st.dataframe(trace_rows(packet_dict["source_trace"]), width="stretch", hide_index=True)

default_decision = default_decision_for_status(packet.status)
decision_options = list(HumanReviewDecision)

with st.form("human_review_form"):
    selected_decision = st.radio(
        "Human review decision",
        options=decision_options,
        index=decision_options.index(default_decision),
        format_func=lambda decision: decision.value,
    )
    override_requires_note = decision_overrides_status(packet.status, selected_decision)
    reviewer_name = st.text_input("Reviewer name", value="Referral Intake Coordinator")
    reviewer_note = st.text_area(
        "Reviewer note" + (" (required for override)" if override_requires_note else ""),
        placeholder=(
            "Required when changing the initial status."
            if override_requires_note
            else "Optional note describing the administrative decision."
        ),
    )
    if override_requires_note:
        st.caption("A note is required because this decision changes the initial status.")
    submitted = st.form_submit_button("Generate reviewed handoff summary")

if submitted:
    if decision_overrides_status(packet.status, selected_decision) and not reviewer_note.strip():
        st.error("Reviewer note is required when overriding the initial status.")
    else:
        reviewed_output = build_reviewed_output(
            packet=packet,
            decision=selected_decision,
            reviewer_note=reviewer_note,
            reviewer_name=reviewer_name or "Referral Intake Coordinator",
        )
        output_path = review_history_output_path(
            selected_bundle_path,
            reviewed_output.reviewed_at,
            reviewed_output.human_review_decision.value,
        )
        save_json_file(output_path, reviewed_output.to_dict())

        st.success(f"Reviewed artifact saved to {output_path}")
        st.subheader("Final Reviewed Handoff Summary")
        st.text(reviewed_output.final_reviewed_handoff_summary)
        st.subheader("Saved Reviewed Output")
        st.json(reviewed_output.to_dict())
