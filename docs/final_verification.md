# Final branch verification

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

The clean branch has **93 tests**. The two additional pending realism-sweep tests
exclude known seeded resources from the found sample and report when all seeds
are unavailable. They are not part of this commit or its test count. The frozen
realism report describes its separate HAPI sample of 10 referrals; the pending
50-referral report is also excluded. Neither sample is the SMART screening count.

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
