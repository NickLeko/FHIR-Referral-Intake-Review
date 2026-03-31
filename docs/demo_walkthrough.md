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

## Where to inspect extracted fields

Open the selected sample bundle in the app and review the `Extracted Review Packet` table. This is the main administrative summary generated from the FHIR-shaped input.

## Where to inspect source traceability

Scroll to the `Source Traceability` table. Each row shows the extracted field name, originating resource type, resource id, and field path used during extraction.

## Where to perform human review

Use the `Human review decision` form near the bottom of the page to:

- confirm ready
- confirm incomplete
- escalate human confirmation
- add an optional reviewer note

Submitting the form writes a reviewed output artifact into `outputs/`.

## Suggested screenshots to capture

- The app with `bundle_001_review_ready.json` selected and the packet visible
- The app with `bundle_003_human_confirmation.json` selected and ambiguity flags visible
- The final reviewed handoff summary after submission
