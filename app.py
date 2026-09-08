from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import sqlite3

import streamlit as st

from src.mapping import build_review_packet
from src.fhir_client import FHIRClient, FHIRClientError
from src.fetch_and_review import fetch_review_packet
from src.bundle_assembler import BundleAssemblyError
from src.writeback import ReviewOutbox, ReviewGateError
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
    "Deterministic referral intake review with source traceability and an explicit human review gate."
)

mode = st.radio("Input source", ["Mock bundles", "Live sandbox"], horizontal=True)
if mode == "Mock bundles":
    bundle_lookup = {path.name: path for path in list_sample_bundle_paths()}
    if not bundle_lookup:
        st.error("No sample bundles were found in data/sample_bundles/.")
        st.stop()
    selected_bundle_name = st.selectbox(
        "Select a mock FHIR bundle", options=list(bundle_lookup)
    )
    selected_bundle_path = bundle_lookup[selected_bundle_name]
    try:
        packet = build_review_packet(parse_bundle(load_json_file(selected_bundle_path)))
    except BundleValidationError as error:
        st.error(f"Bundle validation failed: {error}")
        st.stop()
else:
    st.caption(
        "Uses server and SMART credentials from environment variables. Review submission saves the local artifact and records the disposition on the source sandbox."
    )
    with st.form("live_fetch"):
        service_request_id = st.text_input("ServiceRequest ID")
        fetch_submitted = st.form_submit_button("Fetch referral")
    if fetch_submitted:
        # Clear stale data before attempting a new fetch, including on failure.
        st.session_state.pop("live_packet", None)
        st.session_state.pop("last_delivery", None)
        try:
            client = FHIRClient()
            st.session_state.live_client = client
            st.session_state.live_packet = fetch_review_packet(
                service_request_id.strip(), client=client
            )
        except (
            FHIRClientError,
            BundleAssemblyError,
            BundleValidationError,
            ValueError,
        ) as error:
            st.error(f"Referral could not be loaded. Human follow-up required: {error}")
    if "live_packet" not in st.session_state:
        st.stop()
    packet = st.session_state.live_packet
    selected_bundle_path = Path(packet.bundle_id + ".json")

# Widget choices must belong to the packet the human actually inspected.
context = (mode, packet.bundle_id, repr(packet.input_provenance.to_dict()))
if st.session_state.get("review_context") != context:
    st.session_state.review_context = context
    st.session_state.pop("last_delivery", None)
    st.session_state.pop("decision", None)
    st.session_state.pop("review_note", None)

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
        key="decision",
    )
    override_requires_note = decision_overrides_status(packet.status, selected_decision)
    reviewer_name = st.text_input("Reviewer name", value="Referral Intake Coordinator")
    reviewer_note = st.text_area(
        "Reviewer note (required for override)",
        key="review_note",
        placeholder=(
            "Required when changing the initial status."
            if override_requires_note
            else "Optional note describing the administrative decision."
        ),
    )
    if override_requires_note:
        st.caption(
            "A note is required because this decision changes the initial status."
        )
    submitted = st.form_submit_button(
        "Save review and record disposition on sandbox"
        if mode == "Live sandbox"
        else "Generate reviewed handoff summary",
        disabled=mode == "Live sandbox" and "last_delivery" in st.session_state,
    )

# A repeated browser submission must use the persisted event, even if its
# previous render still showed an enabled submit button.
if submitted and not (mode == "Live sandbox" and "last_delivery" in st.session_state):
    if (
        decision_overrides_status(packet.status, selected_decision)
        and not reviewer_note.strip()
    ):
        st.error("Reviewer note is required when overriding the initial status.")
    else:
        reviewed_output = build_reviewed_output(
            packet=packet,
            decision=selected_decision,
            reviewer_note=reviewer_note,
            reviewer_name=reviewer_name or "Referral Intake Coordinator",
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
        if mode == "Live sandbox":
            try:
                outbox = ReviewOutbox()
                receipt = outbox.enqueue(
                    reviewed_output.to_dict(),
                    base_url=st.session_state.live_client.base_url,
                )
                output_path = Path(receipt["artifact_path"])
                st.session_state.last_delivery = receipt["review_id"]
                outbox.deliver(receipt["review_id"], st.session_state.live_client)
            except (ReviewGateError, FHIRClientError, OSError, sqlite3.Error) as error:
                st.error(
                    f"Unable to save or queue the review: {type(error).__name__}. Inspect local delivery state before retrying."
                )
                st.stop()
        else:
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

if mode == "Live sandbox" and "last_delivery" in st.session_state:
    outbox = ReviewOutbox()
    key = st.session_state.last_delivery
    receipt = outbox.get(key)
    st.subheader("Source server delivery")
    if receipt["state"] == "delivered":
        st.success(f"Disposition recorded and verified: {receipt['task_reference']}")
    else:
        st.warning(
            f"Delivery {receipt['state']}. The local human-reviewed decision is saved; server delivery needs follow-up."
        )
        st.caption(receipt["detail"])
        if receipt.get("retry_at"):
            st.caption(
                "Server retry time: "
                + datetime.fromtimestamp(receipt["retry_at"], timezone.utc).isoformat()
            )
        if st.button("Retry delivery of this saved review"):
            try:
                outbox.deliver(key, st.session_state.live_client)
                st.rerun()
            except (ReviewGateError, OSError, sqlite3.Error) as error:
                st.error(
                    f"Delivery state could not be saved: {type(error).__name__}. Inspect the saved review before retrying."
                )
    st.caption(
        f"Review ID: {key}. Fetch again only to inspect and submit a new review event."
    )
