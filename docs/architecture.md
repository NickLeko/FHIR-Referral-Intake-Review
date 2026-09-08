# Architecture

## Workflow overview

The prototype follows one narrow workflow:

1. A user selects a mock FHIR bundle or fetches one live ServiceRequest with its supported references.
2. The parser accepts only a small supported resource subset.
3. The mapper extracts operationally relevant referral intake fields.
4. Missing and ambiguous elements are detected with deterministic rules.
5. The packet receives a bounded initial status.
6. A human reviewer confirms or overrides the recommendation.
7. A final reviewed handoff summary is saved as a JSON artifact, with mock app reviews written to timestamped files and live reviews to stable review-id filenames.

For the fastest external review, start with the [live round trip](live_task_round_trip.md), the [410 failure observation](live_sandbox_verification.md), then the bundle 006 mock override example.

For live review, `src/auth.py` supplies cached SMART backend-service tokens to
`src/fhir_client.py`. The transport bounds retries, renews once on 401, pins
reference/pagination destinations, and defers long Retry-After delays.
`src/fetch_and_review.py` keeps every batch item at the single-referral boundary.

After explicit human submission, `src/writeback.py` saves the unchanged reviewed
JSON and queues delivery in a local SQLite outbox. It records an additive Task
using conditional create and verifies it by identifier search. Delivery state is
separate from review status. `src/deliver_reviews.py` explicitly replays saved
reviews without generating decisions. See [integration.md](integration.md) for
failure states and recovery; Task is not added to parser inputs.

## Supported resources

- `Patient`
- `ServiceRequest`
- `Practitioner`
- `Condition`
- `Encounter`
- `Observation`
- `DocumentReference`

The parser is intentionally narrow and does not attempt broad FHIR coverage. Each bundle must contain exactly one `ServiceRequest`.

## Parsing and mapping flow

`src/parser.py` validates that the input is a bundle, checks bundle entries, accepts only supported resource types, requires exactly one `ServiceRequest`, and indexes resources by type and reference.

`src/mapping.py` then extracts a referral intake packet from the indexed resources. The mapper focuses on a small set of operational fields:

- intake id / bundle id
- requested service
- referral reason / indication
- ordering provider
- patient age group
- encounter context
- supporting diagnosis
- key observations
- referenced documents
- priority

Explicit `ServiceRequest.reasonReference` values are resolved directly. If a reason reference cannot be resolved, the mapper does not backfill supporting diagnosis from unrelated bundled `Condition` resources. When no `reasonReference` is supplied, the mapper only falls back to a bundled `Condition` when there is exactly one candidate. Unlinked `Observation` and `DocumentReference` resources are ignored unless the `ServiceRequest` references them through `supportingInfo`.

Patient age group is derived against `ServiceRequest.authoredOn` when available, otherwise `Bundle.timestamp`. If neither is usable, the system leaves the field unset instead of using runtime clock time.

## Status logic

The initial status is deterministic and intentionally small:

- `INCOMPLETE` if required intake elements are missing
- `HUMAN_CONFIRMATION_REQUIRED` if the packet is present but ambiguous or includes unsupported elements
- `REVIEW_READY` if required fields are present and no material ambiguity is detected

## Source traceability approach

Each extracted field stores one or more trace entries containing:

- resource type
- resource id
- field path

This keeps the extraction inspectable without introducing full lineage infrastructure.

## HITL review step

The Streamlit app exposes a small review form where the reviewer can:

- confirm ready
- confirm incomplete
- escalate for human confirmation
- add a short reviewer note

The final reviewed output records both the initial status and the human decision.
The JSON shape is documented in `docs/reviewed_output_contract.md` and checked by tests.
The checked-in examples include both standard reviewer confirmations and one explicit override example.

## Design tradeoffs

- Deterministic parsing over generalized parsing: easier to defend and test
- Small resource subset over completeness: more realistic for a portfolio artifact
- One-page UI over platform features: keeps attention on workflow logic
- JSON reviewed artifacts with separate SQLite delivery receipts: the output contract stays independent of delivery state

## Why deterministic parsing was chosen

This project is meant to show inspectable workflow support, not probabilistic interpretation. Deterministic logic makes the mapping explainable, auditable, and easy to test. It also reinforces the HITL boundary by avoiding any suggestion that the system is autonomously interpreting clinical nuance.

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**
