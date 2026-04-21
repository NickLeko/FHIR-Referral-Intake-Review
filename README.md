# FHIR Referral Intake Review

A referral intake coordinator often has to turn structured data, cover sheets, notes, and partial order details into a practical handoff for scheduling, authorization, or specialty routing. This prototype simulates that administrative review step using mock FHIR bundles: it extracts the referral facts that matter, explains missing or ambiguous intake issues, preserves source traceability, and requires a human reviewer before the handoff is finalized.

This repo is a narrow healthcare workflow artifact, not a general FHIR parser and not a clinical decision system. It shows deterministic referral-intake review support: one `ServiceRequest`, a small supported resource subset, conservative evidence use, explicit reviewer confirmation, and auditable JSON outputs.

## Start Here

If you only spend 2 to 3 minutes in the repo, inspect these files in order:

1. [`outputs/bundle_006_override_ready_output.json`](outputs/bundle_006_override_ready_output.json): the strongest reviewed artifact; the system initially escalates because payer context is outside scope, then the reviewer explicitly overrides to `REVIEW_READY`.
2. [`data/sample_bundles/bundle_006_ambiguous_payer_context.json`](data/sample_bundles/bundle_006_ambiguous_payer_context.json): the input bundle behind that override example.
3. [`outputs/bundle_003_output.json`](outputs/bundle_003_output.json): a strong escalation example showing ambiguity handling without override.
4. [`outputs/bundle_001_output.json`](outputs/bundle_001_output.json): the clean baseline case that reaches `REVIEW_READY`.
5. [`docs/reviewed_output_contract.md`](docs/reviewed_output_contract.md) and [`tests/test_output_contract.py`](tests/test_output_contract.py): the executable proof that reviewed artifacts follow a fixed contract.

## What To Look For

- Deterministic scope: exactly one `ServiceRequest`, a fixed supported subset, and no opportunistic inference from unrelated bundle content.
- Human review boundary: the system recommends a status, but a reviewer remains responsible for confirming readiness, confirming incompleteness, or overriding after inspection.
- Auditability: extracted fields carry source traces, reviewed outputs preserve initial status, final status, reviewer identity, reviewer rationale, and review timestamp.

## Why this matters

FHIR can move referral data between systems, but it does not automatically tell an operations team whether the packet is ready for downstream work. A scheduler may need a clear specialty, an authorization team may need a supporting diagnosis, and a referral coordinator may need to confirm the ordering provider before routing the case. This project demonstrates a narrow, inspectable workflow for turning structured referral data into a human-reviewable administrative packet instead of treating interoperability as the finish line.

## What this project demonstrates

- Deterministic parsing of a small subset of FHIR resources
- An explicit single-`ServiceRequest` intake boundary per bundle
- Mapping mock bundle data into a clean referral intake review packet
- Explicit detection of missing, ambiguous, and unsupported elements
- Conservative evidence use: referenced support is preferred and unlinked bundle resources are not treated as evidence by default
- Bounded status classification: `REVIEW_READY`, `INCOMPLETE`, `HUMAN_CONFIRMATION_REQUIRED`
- Source traceability from extracted packet fields back to originating FHIR resources
- An explicit human-in-the-loop review step that can confirm or override the initial classification
- Final reviewed handoff summaries saved as JSON artifacts
- A lightweight reviewed-output contract checked by tests

## What it does not do

- No live FHIR server access
- No SMART-on-FHIR, OAuth, or API integration
- No clinical decision support
- No diagnosis or treatment recommendations
- No production referral management features
- No LLM-dependent core workflow logic

## Supported FHIR resources

- `Patient`
- `ServiceRequest`
- `Practitioner`
- `Condition`
- `Encounter`
- `Observation`
- `DocumentReference`

Each bundle must contain exactly one `ServiceRequest` for the intake packet to be valid.

## Workflow in 30 seconds

1. Select one of seven mock FHIR bundles.
2. The app parses supported resources and extracts referral/order intake details.
3. The system builds an administrative review packet with source traces.
4. Missing or ambiguous fields are surfaced explicitly.
5. The packet receives an initial deterministic status.
6. A human reviewer confirms readiness, confirms incompleteness, or forces escalation.
7. The app saves a timestamped reviewed artifact to `outputs/review_history/`.

## Fastest Demo Path

- Start with `bundle_006_ambiguous_payer_context.json` and compare `outputs/bundle_006_output.json` to `outputs/bundle_006_override_ready_output.json`.
- Then inspect `bundle_003_human_confirmation.json` and `outputs/bundle_003_output.json` to see a non-override escalation case.
- Use the app only after that if you want to watch the packet, issues table, and traceability table render together.

## Status definitions

- `REVIEW_READY`: required intake elements are present and no material ambiguity was detected
- `INCOMPLETE`: required intake elements are missing
- `HUMAN_CONFIRMATION_REQUIRED`: data is present but ambiguous or unsupported enough to require manual clarification

## HITL boundary

The system never claims downstream readiness on its own. It produces an inspectable packet and a recommendation, but a human reviewer remains responsible for confirming readiness, confirming incompleteness, or escalating the case for clarification.

## Source traceability

Each extracted field includes a simple provenance map showing:

- resource type
- resource id
- FHIR field path

This keeps the workflow inspectable and auditable without over-engineering a full lineage system.

Patient age group is derived against `ServiceRequest.authoredOn` when available, otherwise `Bundle.timestamp`. If neither date is usable, the field is left unset rather than derived from wall-clock runtime.

Reviewed output artifacts are described in [docs/reviewed_output_contract.md](docs/reviewed_output_contract.md).

## Repo structure

```text
.
├── README.md
├── app.py
├── data/sample_bundles/
├── docs/
├── outputs/
├── src/
└── tests/
```

## Sample bundles

| Bundle | Scenario | Expected status | Why flagged | Reviewer action |
| --- | --- | --- | --- | --- |
| `bundle_001_review_ready.json` | Cardiology referral with requester, encounter context, diagnosis, observation, and supporting document | `REVIEW_READY` | No required intake gaps or material ambiguity detected | Confirm ready before downstream administrative handling |
| `bundle_002_incomplete.json` | MRI-related referral cover sheet with limited order context | `INCOMPLETE` | Ordering provider, encounter context, and supporting diagnosis are missing | Confirm incomplete and request missing intake elements |
| `bundle_003_human_confirmation.json` | Urgent specialty consult with generic destination, ambiguous reason, and display-only requester | `HUMAN_CONFIRMATION_REQUIRED` | Specialty route, reason, and provider identity require clarification | Escalate for human confirmation before scheduling or authorization work |
| `bundle_004_missing_requester.json` | Otherwise complete orthopedics referral with no requester | `INCOMPLETE` | Ordering provider is missing while diagnosis and encounter context are present | Confirm incomplete and request ordering provider details |
| `bundle_005_unresolved_diagnosis_reference.json` | Neurology referral with an explicit diagnosis reference that cannot be resolved | `INCOMPLETE` | Supporting diagnosis is not inferred from an unrelated bundled condition | Confirm incomplete and request corrected diagnosis support |
| `bundle_006_ambiguous_payer_context.json` | Gastroenterology referral containing a Coverage resource | `HUMAN_CONFIRMATION_REQUIRED` | Payer context is present outside the supported parser subset | Escalate for manual coverage/context clarification |
| `bundle_007_incomplete_patient_demographics.json` | Dermatology referral with missing patient birth date | `INCOMPLETE` | Patient age group cannot be derived | Confirm incomplete and request corrected demographics |

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m src.generate_outputs
streamlit run app.py
```

## Test command

```bash
pytest -q
```

## Demo path

- Start with the checked-in artifacts in `outputs/`; they are the fastest proof surface.
- Inspect `outputs/bundle_006_override_ready_output.json` first, then compare it to `outputs/bundle_006_output.json`.
- Review `data/sample_bundles/bundle_006_ambiguous_payer_context.json` to see the exact input that produced the override example.
- Open the app and inspect the extracted packet, issues table, and source traceability table if you want the interactive walkthrough.
- Use the human review form to generate additional timestamped artifacts in `outputs/review_history/`.

See [docs/demo_walkthrough.md](docs/demo_walkthrough.md) for a guided demo flow.

## Screenshots

Captured locally:

![FHIR Referral Intake Review app overview](screenshots/app_overview.png)

- `screenshots/app_overview.png`
- `screenshots/app_full_page.png`
- `screenshots/app_mobile_like.png`

## Safety and scope boundaries

This project is an administrative workflow realism artifact built on mock data. It is intentionally narrow, non-production, and designed to show deterministic extraction plus human review boundaries rather than automated clinical or operational autonomy.
