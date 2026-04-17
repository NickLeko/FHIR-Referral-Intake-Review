# Demo Walkthrough

## Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m src.generate_outputs
streamlit run app.py
```

## What each sample bundle demonstrates

- `bundle_001_review_ready.json`: a mostly complete referral packet that maps cleanly to `REVIEW_READY`
- `bundle_002_incomplete.json`: a referral missing clear intake elements and classified as `INCOMPLETE`
- `bundle_003_human_confirmation.json`: a packet with present but ambiguous referral details that maps to `HUMAN_CONFIRMATION_REQUIRED`
- `bundle_004_missing_requester.json`: an otherwise complete packet missing the ordering provider
- `bundle_005_unresolved_diagnosis_reference.json`: a packet with an unresolved diagnosis reference that is not backfilled from an unrelated bundled condition
- `bundle_006_ambiguous_payer_context.json`: a packet with payer context outside the supported parser subset
- `bundle_007_incomplete_patient_demographics.json`: a packet with missing birth date, preventing age-group derivation

## Where to inspect extracted fields

Open the selected sample bundle in the app and review the `Extracted Review Packet` table. This is the main administrative summary generated from the FHIR-shaped input.

## Where to inspect source traceability

Scroll to the `Source Traceability` table. Each row shows the extracted field name, originating resource type, resource id, and field path used during extraction.

## Where to perform human review

Use the `Human review decision` form near the bottom of the page to:

- confirm ready
- confirm incomplete
- escalate human confirmation
- add a reviewer note, which is required when changing the initial status

Submitting the form writes a reviewed output artifact into `outputs/`.

## Suggested screenshots to capture

- The app with `bundle_001_review_ready.json` selected and the packet visible
- The app with `bundle_003_human_confirmation.json` selected and ambiguity flags visible
- The final reviewed handoff summary after submission
