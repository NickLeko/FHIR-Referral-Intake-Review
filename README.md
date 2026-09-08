# FHIR Referral Intake Review

A referral intake coordinator often has to turn structured data, cover sheets, notes, and partial order details into a practical handoff for scheduling, authorization, or specialty routing. This integration artifact supports that administrative review step using checked-in mock FHIR bundles or a `ServiceRequest` fetched from a FHIR R4 sandbox: it extracts the referral facts that matter, explains missing or ambiguous intake issues, preserves source traceability, and requires a human reviewer before the handoff is finalized.

This repo is a narrow healthcare workflow artifact, not a general FHIR parser and not a clinical decision system. It shows deterministic referral-intake review support: one `ServiceRequest`, a small supported resource subset, conservative evidence use, explicit reviewer confirmation, and auditable JSON outputs.

## Start Here

If you only spend 2 to 3 minutes in the repo, inspect these files in order:

1. [Live round trip](docs/live_task_round_trip.md#actual-http-results): a human confirmed `INCOMPLETE`; token **200**, conditional Task POST **201**, GET **200**, same-key replay **200**, and exactly **one** identifier match. The Task keeps the same id and version 1. Sandbox identifiers are now stable pseudonyms, including `Task/REDACTED-Task-01`.
2. [Observed fail-closed 410](#failure-semantics): screening checked **2 candidates**; **1** referenced a deleted Patient. That packet was rejected before review/write. The second candidate supported the successful round trip.
3. [Mock bundle walkthrough](docs/demo_walkthrough.md): compare [bundle 006's standard output](outputs/bundle_006_output.json) with its [reviewer override](outputs/bundle_006_override_ready_output.json), then inspect the [fixed local-output contract](docs/reviewed_output_contract.md).

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**

## What To Look For

- Deterministic scope: exactly one `ServiceRequest`, a fixed supported subset, and no opportunistic inference from unrelated bundle content.
- Human review boundary: the system recommends a status, but a reviewer remains responsible for confirming readiness, confirming incompleteness, or overriding after inspection.
- Auditability: extracted fields carry source traces, reviewed outputs preserve initial status, final status, reviewer label, reviewer rationale, and review timestamp.

## Why this matters

FHIR can move referral data between systems, but it does not automatically tell an operations team whether the packet is ready for downstream work. A scheduler may need a clear specialty, an authorization team may need a supporting diagnosis, and a referral coordinator may need to confirm the ordering provider before routing the case. This project demonstrates a narrow, inspectable workflow for turning structured referral data into a human-reviewable administrative packet instead of treating interoperability as the finish line.

## What this project demonstrates

- Deterministic parsing of a small subset of FHIR resources
- An explicit single-`ServiceRequest` intake boundary per bundle
- Mapping mock or live-assembled Bundle data into a clean referral intake review packet
- SMART Backend Services OAuth2 client credentials against SMART Health IT, with token renewal
- Narrow reference assembly from a FHIR R4 endpoint
- Additive, idempotent Task write-back after explicit human review
- Durable per-review delivery receipts and bounded recovery from partial failures
- Explicit detection of missing, ambiguous, and unsupported elements
- Conservative evidence use: referenced support is preferred and unlinked bundle resources are not treated as evidence by default
- Bounded status classification: `REVIEW_READY`, `INCOMPLETE`, `HUMAN_CONFIRMATION_REQUIRED`
- Source traceability from extracted packet fields back to originating FHIR resources
- An explicit human-in-the-loop review step that can confirm or override the initial classification
- Final reviewed handoff summaries saved as JSON artifacts
- A lightweight reviewed-output contract checked by tests

## What it does not do

- No interactive SMART EHR launch or authenticated reviewer identity
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

Each bundle must contain exactly one `ServiceRequest` for the intake packet to be valid. `Task` is an output resource only; the supported input subset is unchanged.

## Workflow in 30 seconds

1. Select one of seven mock FHIR bundles, or fetch one live sandbox ServiceRequest.
2. The app parses supported resources and extracts referral/order intake details.
3. The system builds an administrative review packet with source traces.
4. Missing or ambiguous fields are surfaced explicitly.
5. The packet receives an initial deterministic status.
6. A human reviewer confirms readiness, confirms incompleteness, or forces escalation.
7. The app saves a reviewed artifact to `outputs/review_history/`. In live mode it also records and verifies a Task on the source server, with delivery tracked separately.

## Mock Demo Path

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

The packet also includes `input_provenance`. It identifies mock versus live input and, for each fetched resource, records the server base URL, resource type and id, `meta.versionId`, `meta.lastUpdated`, and fetch timestamp when available. Live provenance also notes that reverse references were not searched and identifies out-of-scope reference field paths that were intentionally ignored. Provenance does not participate in status classification.

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
├── scripts/
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

## Authenticated sandbox and write-back

The authenticated target is **SMART Health IT**: its public R4 launcher supports backend-service client credentials with signed assertions and registered public keys, and advertises Task conditional creation and identifier search. The existing open HAPI read mode remains available.

After installing dependencies, create and load a local test registration:

```bash
python scripts/setup_smart_sandbox.py
source .env.smart
streamlit run app.py
```

The helper generates an RSA key and matching public registration. Runtime credentials come from environment variables; `.env.smart` is ignored and restricted to its owner. Keep this file while reviews are pending. Full variables, scopes, registration details and recovery commands are in [docs/integration.md](docs/integration.md).

Auth uses `grant_type=client_credentials` with an RS384 signed client assertion. Tokens stay in memory and are renewed before expiry by acquiring a new client-credentials token. An unexpected 401 permits one reacquisition and retry; persistent auth failures stop access. This flow does not use refresh tokens or an interactive SMART launch.

In Streamlit select **Live sandbox**, fetch a ServiceRequest and inspect its packet. A human must submit the review form; overrides still require a note. The unchanged reviewed-output JSON is saved first. An additive `Task` then references the original ServiceRequest through `focus`, records the final disposition in `businessStatus`, and includes the reviewer decision, note and time. `Task.status=completed` means the review action finished, not that the referral is ready or approved.

A durable SQLite outbox tracks delivery separately from the reviewed JSON contract. Conditional creation with a stable review identifier prevents duplicate Tasks on replay, assuming server conformance. A source-server lookup verifies the contents before marking delivery successful. Use **Retry delivery of this saved review** or the CLI to recover; do not submit a new review just to retry:

```bash
python -m src.deliver_reviews
python -m src.deliver_reviews --review-id SAVED_REVIEW_ID
python -m src.deliver_reviews --retry-pending
```

Only existing human-reviewed live artifacts can enter delivery. No fetch, batch, or retry path invents a reviewer decision. The original ServiceRequest is not modified.

## Live read mode

Fetch one `ServiceRequest`, assemble only the references consumed by the existing parser, and write the extracted packet to the ignored `outputs/live/` directory:

```bash
python -m src.fetch_and_review --service-request <id>
```

Without SMART configuration, the default is the open `https://hapi.fhir.org/baseR4` endpoint. Override it with `FHIR_BASE_URL` or `--base-url` (with SMART enabled, these must match):

```bash
FHIR_BASE_URL=https://example.test/fhir \
  python -m src.fetch_and_review --service-request <id>
```

In a separate shell with SMART credentials unset, create temporary demo data on an open test server by posting the seven checked-in synthetic Bundles as transactions and capture the server-assigned `ServiceRequest` ids:

```bash
python scripts/seed_sandbox.py
```

The seed script performs writes and should be used only against a test sandbox. Keep returned ids locally for the optional seeded comparison below.

Run an aggregate-only realism sweep over up to 50 found sandbox `ServiceRequest` resources. Optionally supply known seed ids repeatedly; those are excluded from the found sample and reviewed separately. Replace the placeholders with ids kept locally:

```bash
python scripts/realism_sweep.py --limit 50 \
  --seeded-service-request-id YOUR_FIRST_SEED_ID \
  --seeded-service-request-id YOUR_SECOND_SEED_ID
```

Omit the seed arguments for a found-only sweep; retention then remains unchecked. The report compares status and presence of the six expected intake elements. Seed ids are validated and deduplicated, and neither ids nor patient-level values appear in the report. SMART registration URLs are pseudonymized in report headers.

The sweep writes [docs/realism_sweep.md](docs/realism_sweep.md) without retaining raw server resources, resource ids, or patient-level values. Both live commands use the same deterministic `parse_bundle` and `build_review_packet` path as the checked-in mock Bundles. The fetch CLI produces an extracted packet awaiting human review; it does not fabricate a reviewer decision.

## Reference-integrity measurement

The separate read-only [reference-integrity validator](docs/reference_integrity.md)
samples a chosen R4 resource type, walks its standard Reference fields, and
reports resolution by target type, field path, and source resource. It reuses
the existing auth/fetch layer with pagination, pacing, backoff, and a per-run
cache. It does not expand the intake parser or change the human review gate.

```bash
source .env.smart
python -m src.reference_integrity --resource-type ServiceRequest --sample-size 100
```

The [two live SMART Health IT samples on 2026-09-08 UTC](docs/reference_integrity_comparison.md)
resolved **11/36 distinct targets (30.56%)** in the original contiguous cohort
and **10/116 (8.62%)** in a scattered sample. These rates describe the queried
targets' state. Downstream exposure was **22/272 occurrences (8.09%) from those
36 targets**, with 236 cache hits, versus **17/291 (5.84%) from those 116
targets**, with 175 cache hits. Repeated references reuse the same lookup:
occurrence rates weight target failures by their impact on these source samples.

The original **82/100 referrals with a broken reference** were heavily
clustered: 76 shared the same deleted Patient, Practitioner, and Encounter trio.
The second sample scanned all **8,831** returned ServiceRequests, skipped the
first 100, and selected 100 across the remaining 8,731 using a fixed-seed
reservoir. **95/100** had broken references; its largest shared broken-target
set involved 11 referrals. The problem extends beyond the first cluster, but
these observations do not establish independent failure mechanisms per type,
a common deletion event, or production prevalence. Reports preserve separate
logical/display-only counts and use pseudonyms, not sandbox lookup ids.

## Failure semantics

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**

Default retries are an initial attempt plus two transient retries, with 0.25/0.5-second exponential backoff and a 10-second request timeout. Delivery failures never alter a human's saved disposition.

| Condition | Behavior |
| --- | --- |
| Server 500 mid-batch | Bounded retries per request. An exhausted read fails that packet closed, including failed support fetches. Other referrals continue independently. Writes reconcile by identifier after retry exhaustion. |
| Token expires between read and write | Renew before expiry; on 401 reacquire once and retry the same conditional write. Persistent failure requires human follow-up; never fall back to anonymous access. |
| Write succeeds but response is lost | Reuse the same conditional-create identifier and verify the stored Task. If delivery cannot be confirmed, retain `uncertain` for human reconciliation/replay. |
| Rate limiting | Honor Retry-After seconds or HTTP date. A delay beyond the 5-second synchronous cap defers work instead of retrying early; outbox cooldown survives restart and applies across the batch. |
| Malformed Bundle/resource shape | No schema-error retry. Fail the affected packet/write closed; malformed post-write verification stays uncertain. Human investigates the source. |
| Some batch writes land, others fail | Persist per-review receipts, retain successful writes, and skip them on replay. Failed/uncertain items need human follow-up. No rollback or blanket success. |

**Observed live: sandbox lifecycle and fail-closed review.** Disappearing seeded resources and dangling Patient references are the same sandbox lifecycle behavior observed two ways: resources can disappear independently of their references. On 2026-09-07 PDT, SMART Health IT returned **200** for `ServiceRequest/REDACTED-ServiceRequest-01` but **410 Gone** for `Patient/REDACTED-01`, explicitly reporting deletion; assembly stopped and no Task was sent. The separate HAPI n=50 sweep (2026-09-04 UTC) still found all **7 seeds** at its measurement, which does not guarantee later availability. Its **50 found referrals were all `INCOMPLETE`**, with **41/50 (82%)** containing only one or two of six expected elements; the seeded comparison produced **2 `REVIEW_READY`, 4 `INCOMPLETE`, and 1 `HUMAN_CONFIRMATION_REQUIRED`**. These describe sandbox data, not real-world referral completeness, and do not establish a shared cleanup event or deletion actor. See the [aggregate realism findings](docs/realism_sweep.md) and [live 410 response](docs/live_sandbox_verification.md).

The read CLI accepts repeated `--service-request` arguments, producing separate single-referral packets and a per-item manifest. Delivery batches accept only saved reviewed events and return nonzero on any unresolved outcome. See [failure and recovery details](docs/integration.md#failure-semantics).

## Test command

See the [final verification record](docs/final_verification.md) for the clean-branch test count and validation scope.

```bash
pytest -q
```

## Interactive mock demo

- After the live evidence above, use the checked-in mock artifacts in `outputs/` for a reproducible walkthrough.
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

This is a deterministic administrative integration artifact built on synthetic data and untrusted public-sandbox test data. It has no clinical recommendations or autonomous operational decisions.

**It is not production-grade.** Reviewer names are unverified labels; there is no RBAC, signed approval/audit, KMS/key rotation, encrypted managed data store, distributed delivery worker, full FHIR/profile validation, source-version concurrency guard, or production privacy/security certification. A source may change during review, and competing review events require manual reconciliation. The public sandbox cannot demonstrate production authorization guarantees.

**Live round trip verified (2026-09-07 PDT / 2026-09-08 UTC).** Screening checked **2 candidates**: **1** failed on a dangling Patient (410); the second, `ServiceRequest/REDACTED-ServiceRequest-02`, had a fully resolvable supported reference chain (200s). Nick Leko explicitly confirmed its `INCOMPLETE` packet before write-back. The real token response granted all requested scopes, including `system/Task.crs`.

The first conditional Task POST returned **201 Created**, id **`REDACTED-Task-01`** (a post-capture pseudonym). GET `/Task/REDACTED-Task-01` returned **200**, and every submitted field matched, including `completed`, `INCOMPLETE`, `CONFIRM_INCOMPLETE`, the reviewer, and the source ServiceRequest reference. No extensions were sent or returned. Repeating the identical conditional write returned **200**, the **same id and version 1**; a final identifier search returned **200**, `total: 1`. See the [full live round-trip record and server response](docs/live_task_round_trip.md).

The earlier fail-closed 410 remains a verified source-data failure observation, described under [Failure semantics](#failure-semantics). Earlier implementation notes report renewal, invalid-signature rejection, and advertised Task capabilities; those checks were not independently repeated in this final pass. Lost write responses, deliberately injected 500/429 failures, expiry between read/write, partial write batches, and concurrency behavior remain outside this live proof; see the [verification limits](docs/integration.md#verification-and-remaining-limitations).
