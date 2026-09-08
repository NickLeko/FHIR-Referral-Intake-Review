# Branch verification records

## Reference-integrity validator

Verified on 2026-09-08 UTC on `codex/fhir-reference-integrity`, branched from
main at `fc8b60b` after both earlier merges.

- `pytest -q`: **121 passed**, including **26** reference-integrity cases and
  the existing Streamlit review-flow AppTests.
- `ruff check --select F .`: passed.
- New mocked-server tests cover 200/404/410/500/403, caching, typed display-only
  and logical references, extensions, contained targets, pagination and partial
  sampling, 429 backoff/deferral, malformed responses, version-specific targets,
  unsafe URLs, pacing, CLI output redaction, and malformed reference inventory.
- Live sample 1: 100 contiguous ServiceRequests, **11/36 distinct targets
  resolved (30.56%)**. Occurrence resolution: **22/272 (8.09%) from those 36
  targets**, with **236 cache hits**; 82/100 sources had a broken reference.
  Distinct outcomes: 11 HTTP 200, 23 HTTP 410, 2 HTTP 404. The largest shared
  broken-target set was one deleted trio referenced by 76 sources.
- Live sample 2: fixed-seed reservoir after skipping the first 100 of **8,831**
  unique sources across **177 pages**. Selected 100 of **8,731** eligible sources
  at positions 130–8,825 with no adjacent pairs. **10/116 distinct targets
  resolved (8.62%)**. Occurrence resolution: **17/291 (5.84%) from those 116
  targets**, with **175 cache hits**; 95/100 sources had a broken reference.
  Distinct outcomes: 10 HTTP 200, 105 HTTP 410, 1 HTTP 404. The largest shared
  broken-target set involved 11 sources. See the [comparison](reference_integrity_comparison.md).
- Added tests for reservoir selection across page boundaries, exclusion of the
  skipped prefix, deterministic selection, short populations, scan limits, and
  distinct-target clustering versus repeated occurrences.
- Live reports contain only run-local resource pseudonyms and a redacted SMART
  registration path. No raw payloads or logical/display values are retained.
  The [measurement record](reference_integrity_live_2026-09-08.md) and
  [per-reference JSON](reference_integrity_live_2026-09-08.json) preserve the
  actual run's timestamps and observations.

Injected errors remain mock-tested. This run made no Task writes and adds no
concurrent-idempotency evidence. Earlier records below retain their historical
test counts and the separate two-candidate write-back verification.

## Realism-sweep follow-up

Verified on 2026-09-08 UTC on `codex/fhir-realism-sweep`, branched from updated
main at `5237855`. The previously separate reporting changes are now included.

- `pytest -q`: **95 passed**, including the six realism-sweep tests.
- `pytest -q tests/test_realism_sweep.py`: **6 passed**.
- `ruff check --select F .`: passed.
- Sweep tests cover pagination/limit, aggregate status and field-presence counts,
  seeded-versus-found exclusion, repeated CLI seed arguments and deduplication,
  unavailable-seed wording, aggregate file output, and registration redaction.
- Generated a report from offline synthetic fixtures and checked that source,
  seed and fixture resource ids were absent. SMART registration values are
  pseudonymized in report headers. The historical n=50 findings contain only
  aggregates and no sandbox record identifiers.
- Preserved the 2026-09-04 HAPI findings: 50/50 found referrals `INCOMPLETE`,
  41/50 with one or two of six expected elements; seven retained seeds with
  2 `REVIEW_READY`, 4 `INCOMPLETE`, and 1 `HUMAN_CONFIRMATION_REQUIRED`.
  This was not a fresh live sweep. All seven seeds were available at that
  measurement; the report does not claim they disappeared during that run.

The README now joins seed retention and the live dangling-Patient 410 in one
lifecycle observation. The SMART result remains **2 candidates**, **1** dangling
reference, and `Task/REDACTED-Task-01`: token **200**, POST **201**, GET **200**,
same-key replay **200** (same id/version 1), identifier search **200**, `total: 1`.
Injected 500/429 failures, response loss, token expiry between read/write, and
partial batch failure remain mock-tested only; concurrent uniqueness remains
unverified. This reporting change does not expand parser inputs or authorize
Task delivery without human review.

## Auth/write-back verification at `5237855`

Verified on 2026-09-08 UTC for `codex/fhir-auth-writeback`. The implementation
is based on `b74ad46`; the only Python change in this final pass removes two
unused imports from `tests/test_bundle_assembler.py`. The remaining changes
correct and publish documentation. Pre-existing realism-sweep edits are excluded.

## Checks performed

- `ruff check --select F .`: passed (all Pyflakes rules; not a formatter or an
  all-rule Ruff run).
- `pytest -q`: **93 passed** in an isolated checkout of the committed code with
  the import removal applied, without the pending realism-sweep edits. This
  includes three Streamlit AppTest tests covering the mock override gate, saved
  contract, mocked live delivery/retry, and clearing a failed refetch's form.
- Started Streamlit on `127.0.0.1:8767` and inspected it in a browser. The packet,
  issues, source traces, and human review form rendered. A local mock submission
  saved its JSON and displayed the final reviewed handoff summary. This browser
  check did not contact or write to a FHIR sandbox.
- Audited README and every document in `docs/` against the parser, mapper, auth,
  transport, review gate, outbox, CLIs, app, tests, and retained live evidence.
  Removed misleading filename/storage wording and clarified the token-scope
  omission behavior. No current claim denying live FHIR access, backend OAuth,
  or Task API integration remains. The historical failed-attempt record is
  explicitly distinguished from the later successful run.

At `5237855`, the clean branch had **93 tests**. The two then-pending realism-sweep tests
exclude known seeded resources from the found sample and report when all seeds
are unavailable. They were not part of that commit or its test count. Its realism report described
a separate HAPI sample of 10 referrals; the then-pending 50-referral report was
also excluded. Neither sample is the SMART screening count.

## Consistent live results

These are retained observations of the September 7 PDT / September 8 UTC run,
not a fresh sandbox run during the final pass. All sandbox identifiers below
are stable post-capture pseudonyms, consistently used in the evidence and docs.

| Figure | Verified value |
| --- | --- |
| SMART referral candidates checked | **2** |
| Rejected for dangling Patient reference | **1**, HTTP **410** |
| Selected source | `ServiceRequest/REDACTED-ServiceRequest-02`; present supported references resolved with **200** |
| Token acquisition | **200**, exact requested/granted scope match including `system/Task.crs` |
| Initial conditional Task POST | **201**, `Task/REDACTED-Task-01` |
| GET by id | **200**, every submitted field matched |
| Same-key conditional replay | **200**, same Task id and version **1** |
| Identifier search | **200**, `total: 1` |
| Human disposition | `CONFIRM_INCOMPLETE`, final status `INCOMPLETE`; Task status `completed` |
| Extensions | None sent or returned; nonempty extensions unverified |

See the [round-trip record](live_task_round_trip.md) and the
[historical 410 observation](live_sandbox_verification.md). The Task id and
idempotency key are deliberately no longer published as sandbox lookup values.

**Verification boundary:** Token acquisition with granted write scope, conditional
Task create, read-back, and sequential replay were confirmed live, as was the
410 fail-closed behavior. Lost responses, injected 500s, rate limiting (429),
expiry between read/write, and partial batch failure are mock-tested only.
**Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**
The mock's sequential dictionary implementation is not evidence of server
atomicity under races.

## Hygiene and audit limits

Scanned all **151 reachable Git blobs** before the final commit plus the proposed
publishable files for the configured credential values, private-key material,
JWTs, and common access-token patterns. No credentials were found. Reachable
history contains no numeric/UUID sandbox resource references. Checked-in mock
bundles, response fixtures, outputs and screenshots use authored synthetic data
and fixture ids; they are not captures of the live sandbox records.

All **12 local evidence JSONs** have a `redaction_note` declaring post-capture
pseudonymization. Patient references, other resource ids (including Task and
ServiceRequest), business/search identifiers, and registration identifiers are
pseudonymized consistently. Bearer credentials and client assertions are redacted.
Response bodies remain structurally inspectable; captured Content-Length values
refer to the original bytes. These edited evidence files are not replay inputs.

`.gitignore` covers `.env`, `.env.*` except the placeholder-only `.env.example`,
private key files, Streamlit secrets, `outputs/live/`, `outputs/review_history/`,
and `outputs/integration/`. No evidence JSONs or runtime credentials are staged.
The configured `.env.smart` and operational reviewed JSON/outbox retain original
values locally for authenticated operation and safe replay; they are ignored
and are outside the publishable-evidence certification. This audit is not a
claim that a functioning local credential store contains no secrets.

Historical implementation notes also report discovery/capability checks,
invalid-signature rejection, and explicit token invalidation/reacquisition.
Those observations cannot be proved from code alone and were not independently
rerun here. The captured round trip does not establish source retention,
production authorization, concurrent uniqueness, coherent source snapshots,
authenticated reviewer identity, or suitability for patient care.
