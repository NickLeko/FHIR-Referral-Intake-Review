# Reviewed Output Contract

Reviewed outputs are local JSON artifacts written to `outputs/` after human review.
They are not FHIR resources and are not system-of-record updates.

## Top-level fields

- `bundle_id`: source bundle id
- `extracted_review_packet`: deterministic packet generated before human review
- `status_before_review`: packet status before reviewer action
- `missing_elements`: mirror of `extracted_review_packet.missing_elements`
- `ambiguous_elements`: mirror of `extracted_review_packet.ambiguous_elements`
- `fields_requiring_human_confirmation`: mirror of the same packet field
- `issue_rationales`: mirror of `extracted_review_packet.issue_rationales`
- `source_trace_map`: mirror of `extracted_review_packet.source_trace`
- `human_review_decision`: reviewer action
- `reviewer_name`: reviewer label entered in the app or generated fixture
- `reviewer_note`: reviewer note; required when overriding the initial status
- `reviewed_at`: ISO timestamp
- `final_status`: status after human review
- `final_reviewed_handoff_summary`: administrative summary text
- `recommended_next_admin_step`: final next administrative step

## Extracted review packet fields

- `intake_id`
- `bundle_id`
- `requested_service`
- `referral_reason`
- `ordering_provider`
- `patient_age_group`
- `encounter_context`
- `supporting_diagnosis`
- `key_observations`
- `referenced_documents`
- `priority`
- `missing_elements`
- `ambiguous_elements`
- `fields_requiring_human_confirmation`
- `unsupported_elements`
- `issue_rationales`
- `source_trace`
- `recommended_next_admin_action`
- `status`

## Required invariants

- `status_before_review` must match `extracted_review_packet.status`.
- Mirrored top-level issue and trace fields must match the extracted packet.
- `final_status` must match `human_review_decision`.
- `reviewer_note` is required when `human_review_decision` overrides `status_before_review`.
- `source_trace` entries use `resource_type`, `resource_id`, and `field_path`.
- `issue_rationales` entries use `field`, `issue_type`, `rationale`, `source`, and `evidence`.
- Accepted packet statuses are `REVIEW_READY`, `INCOMPLETE`, and `HUMAN_CONFIRMATION_REQUIRED`.
- Accepted review decisions are `CONFIRM_READY`, `CONFIRM_INCOMPLETE`, and `ESCALATE_HUMAN_CONFIRMATION`.

The executable version of this contract lives in `src/contracts.py` and is checked
against generated and checked-in outputs by the test suite.
