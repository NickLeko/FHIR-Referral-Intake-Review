# Reviewed Output Contract

Reviewed outputs are local JSON artifacts.
The app writes timestamped mock review-history files into `outputs/review_history/` and stable review-id files into `outputs/review_history/live/`; deterministic checked-in examples live in `outputs/`.
The JSON artifacts are not FHIR resources. For human-reviewed live inputs, additive Task delivery records the disposition on the source sandbox; delivery receipts live in a separate SQLite outbox and add no keys to this contract. See [integration.md](integration.md).

The live fetch CLI writes the extracted review-packet portion of this contract to
`outputs/live/`. It does not add a human-review decision or represent the packet as
finalized.

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
- `final_reviewed_handoff_summary`: compact operational handoff summary text
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
- `input_provenance`

## Input provenance

`input_provenance` is additive packet metadata and does not affect extraction,
missing or ambiguous detection, or status classification.

- `source_type`: `mock` or `live`
- `resources`: one record for each resource fetched with an HTTP GET
- `scope_notes`: non-status-bearing notes about intentionally unassembled references

Each live resource record uses:

- `server_base_url`
- `resource_type`
- `resource_id`
- `version_id`: the resource's `meta.versionId`, or `null`
- `last_updated`: the resource's `meta.lastUpdated`, or `null`
- `fetched_at`: the fetch timestamp

Live packets state that reverse references were not searched and identify the field
paths of forward references outside the supported assembly boundary. The notes do
not contain referenced resource ids and do not affect classification.

Newly generated mock packets use `source_type: mock` with empty resource and scope-note lists.
Previously generated reviewed artifacts that omit `input_provenance` remain valid;
this preserves backward compatibility for the additive contract change.

## Required invariants

- `status_before_review` must match `extracted_review_packet.status`.
- Mirrored top-level issue and trace fields must match the extracted packet.
- `final_status` must match `human_review_decision`.
- `reviewer_note` is required when `human_review_decision` overrides `status_before_review`.
- `source_trace` entries use `resource_type`, `resource_id`, and `field_path`.
- When present, `input_provenance.source_type` must be `mock` or `live`, each resource record must follow the field shape above, and `scope_notes` must be a list of strings.
- `issue_rationales` entries use `field`, `issue_type`, `rationale`, `source`, and `evidence`.
- Accepted packet statuses are `REVIEW_READY`, `INCOMPLETE`, and `HUMAN_CONFIRMATION_REQUIRED`.
- Accepted review decisions are `CONFIRM_READY`, `CONFIRM_INCOMPLETE`, and `ESCALATE_HUMAN_CONFIRMATION`.

The executable version of this contract lives in `src/contracts.py` and is checked
against generated and checked-in outputs by the test suite.
