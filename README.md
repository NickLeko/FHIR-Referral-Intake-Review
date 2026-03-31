# FHIR Referral Intake Review

A simulated healthcare interoperability workflow prototype that ingests mock FHIR bundles, extracts referral intake details into an operational review packet, flags gaps or ambiguity, and routes the result into an explicit human-review step.

## Why this matters

FHIR-shaped data is often discussed as an interoperability standard, but operational teams still need the data transformed into something inspectable and actionable. This project demonstrates a narrow but realistic bridge from structured referral data to a human-reviewable administrative handoff.

## What this project demonstrates

- Deterministic parsing of a small subset of FHIR resources
- Mapping mock bundle data into a clean referral intake review packet
- Explicit detection of missing, ambiguous, and unsupported elements
- Bounded status classification: `REVIEW_READY`, `INCOMPLETE`, `HUMAN_CONFIRMATION_REQUIRED`
- Source traceability from extracted packet fields back to originating FHIR resources
- An explicit human-in-the-loop review step that can confirm or override the initial classification
- Final reviewed handoff summaries saved as JSON artifacts

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

## Workflow in 30 seconds

1. Select one of three mock FHIR bundles.
2. The app parses supported resources and extracts referral/order intake details.
3. The system builds an administrative review packet with source traces.
4. Missing or ambiguous fields are surfaced explicitly.
5. The packet receives an initial deterministic status.
6. A human reviewer confirms readiness, confirms incompleteness, or forces escalation.
7. A reviewed handoff summary is saved to `outputs/`.

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

- `bundle_001_review_ready.json`: mostly complete and review-ready
- `bundle_002_incomplete.json`: missing clear operational intake elements
- `bundle_003_human_confirmation.json`: present but ambiguous enough to require manual confirmation

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

- Open the app and select each sample bundle from the dropdown
- Inspect the extracted packet and source traceability table
- Use the human review form to confirm or override the recommendation
- Review the saved JSON artifacts in `outputs/`

See [docs/demo_walkthrough.md](/Users/nicholasleko/projects/FHIR-Referral-Intake-Review/docs/demo_walkthrough.md) for a guided demo flow.

## Screenshots

Captured locally:

- `screenshots/app_overview.png`
- `screenshots/app_full_page.png`
- `screenshots/app_mobile_like.png`

## Safety and scope boundaries

This project is an administrative workflow realism artifact built on mock data. It is intentionally narrow, non-production, and designed to show deterministic extraction plus human review boundaries rather than automated clinical or operational autonomy.
