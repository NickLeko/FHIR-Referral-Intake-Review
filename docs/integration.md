# SMART auth and reviewed disposition delivery

## Sandbox choice and setup

The authenticated target is **SMART Health IT's public R4 launcher**. It provides
SMART Backend Services (`grant_type=client_credentials`) with asymmetric client
authentication and an R4 proxy advertising Task conditional creation and identifier
search. The old HAPI open-endpoint mode remains available for read experiments.
An open HAPI request does not test OAuth.

Primary references:

- [SMART Backend Services](https://hl7.org/fhir/smart-app-launch/backend-services.html)
- [SMART Health IT launcher](https://github.com/smart-on-fhir/smart-launcher-v2)
- [Launcher client assertion verification](https://github.com/smart-on-fhir/smart-launcher-v2/blob/main/backend/routes/auth/token.ts)
- [Launcher registration encoding](https://github.com/smart-on-fhir/smart-launcher-v2/blob/main/src/isomorphic/codec.ts)
- [FHIR R4 conditional create](https://hl7.org/fhir/R4/http.html#ccreate)
- [FHIR R4 Task](https://hl7.org/fhir/R4/task.html)

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_smart_sandbox.py
source .env.smart
streamlit run app.py
```

The setup command performs no network writes. It generates a fresh 2048-bit RSA
key and client id, registers **only the public JWK** in the launcher's encoded
`/sim/` URL, and writes shell exports into `.env.smart` with mode `0600`. This
sandbox registration encoding is specific to the launcher; it is not an OAuth
dynamic registration protocol. The helper follows the official encoding linked
above. It deliberately refuses to overwrite an existing file: keep the same
registration and destination while saved reviews are pending.

Do not use the unconfigured `/v/r4/fhir` launcher URL for an authentication proof:
the launcher can skip signature checks when no JWKS is registered. The helper
includes a public JWKS so signature checks run. This is still a public test
sandbox with permissive registration, not a production authorization service.

All runtime credentials come from environment variables:

| Variable | Meaning |
| --- | --- |
| `FHIR_AUTH_MODE` | `smart` for backend-service OAuth; `none` (default) for legacy open access |
| `FHIR_BASE_URL` | Exact registered FHIR base, including the sandbox `/sim/` path |
| `FHIR_TOKEN_URL` | Exact HTTPS token endpoint for that registration; manually compare with discovery (the client does not discover it) |
| `FHIR_CLIENT_ID` | Registered backend-service client identity |
| `FHIR_KEY_ID` | Public JWK `kid` |
| `FHIR_PRIVATE_KEY_PEM` | Multiline RSA private key, held in process memory |
| `FHIR_SCOPES` | Optional subset of the default scopes below |

The default scope request is `.rs` (read/search) for `Patient`, `ServiceRequest`,
`Practitioner`, `Condition`, `Encounter`, `Observation`, and `DocumentReference`,
plus `system/Task.crs` (create/read/search). Broader scopes are rejected. `Task`
is **output only** and is not added to the parser or graph assembly subset.
Seeding unrelated resources is not a permission of this integration client.

`.env`, `.env.*`, private-key files, live artifacts, review history, and the outbox
are gitignored. `.env.example` contains placeholders only. Never paste tokens or
keys into code, command-line arguments, screenshots, or bug reports. The app does
not automatically load dotenv files: source the file in the same shell that
starts the app or supply the variables using a secret manager. A partial SMART
configuration fails closed; configured credentials never cause an anonymous
fallback. With SMART enabled, `--base-url` must match `FHIR_BASE_URL`.

## Auth lifecycle

`src/auth.py` signs RS384 assertions with `iss=sub=client_id`, the token endpoint
as `aud`, a five-minute maximum lifetime, and a new `jti` on each attempt. It
submits form-encoded client credentials and never uses an LLM.

Access tokens are cached in memory using a monotonic expiry deadline, with an
early-renewal margin of the smaller of 30 seconds and 10% of the token lifetime.
Renewal obtains a **new client-credentials token**. This grant does not use a
refresh token or an end-user authorization-code flow. A server-side 401 allows
one token invalidation and reacquisition per FHIR operation; another 401 fails
closed. Token acquisition has the same bounded transient retry policy as reads.
Malformed token responses and explicitly insufficient granted scopes block access. If the token response omits `scope`, the client assumes the requested scopes; the recorded live run instead checked an explicit returned scope set for exact equality.

The token URL is explicitly configured (and checked against sandbox discovery in
manual verification); the client does not trust arbitrary discovered endpoints
with its assertion. HTTPS is required for authenticated traffic, requests do not
follow redirects, and reference/pagination resolution remains pinned to the
configured FHIR base. Remote response bodies and credentials are excluded from
user-facing failure messages. These measures are not a full security program.

## Read, human review, and write

1. In Streamlit choose **Live sandbox**, enter a sandbox `ServiceRequest` id and
   select **Fetch referral**. Use synthetic test data only. The app assembles the
   same narrow forward-reference graph and shows the packet, issues and traces.
2. A human inspects the packet, chooses one of the existing three decisions, and
   supplies a note for an override. Select **Save review and record disposition
   on sandbox**. Fetching or a `REVIEW_READY` recommendation alone never writes.
3. The unchanged reviewed-output JSON is saved under
   `outputs/review_history/live/<review-id>.json` using atomic replacement. A
   committed SQLite outbox row in `outputs/integration/outbox.sqlite3` precedes
   any FHIR write. If local persistence fails, sending does not begin.
4. A Task records the completed **review action**. `Task.status=completed` does
   not mean the referral is clinically complete, approved, scheduled, or ready.
   `businessStatus.text` holds the reviewer's final packet status; `output`
   records the decision, original recommendation, and next administrative step.
   `focus.reference=ServiceRequest/<original-id>` connects it to the referral.
   Reviewer label, note, and time accompany the Task. The ServiceRequest is not
   modified. Existing source version/timestamp provenance stays in local JSON.
5. Delivery is displayed separately as `pending`, `delivered`, `needs_attention`,
   or `uncertain`. Delivery failures never change the human disposition. After
   submission, retry the saved review rather than submitting a new decision.

A Task does not guarantee a source EHR will surface or act on the result; that
requires an agreed server workflow/profile. A later human review creates a new
append-only event; this artifact does not resolve competing reviews or mark old
Tasks as superseded.

The existing read CLI remains available. Repeating the argument processes
independent referrals and writes a per-item `fetch_batch.json` manifest:

```bash
python -m src.fetch_and_review --service-request ID1 --service-request ID2
```

Successful items await human review; no batch path fabricates reviewer decisions.
The CLI exits nonzero if any item fails. Use the current manifest when consuming
packet files: a failed re-fetch does not erase an older saved packet. The UI
clears its old packet before a new fetch, so a failed fetch cannot reuse a stale
review form.

For open HAPI experiments, start a separate shell with SMART credential variables
unset. The existing `scripts/seed_sandbox.py` posts synthetic transaction Bundles
to an **open** test server only and has no automatic non-idempotent retries. It
is separate from reviewed Task delivery. To use its seven synthetic bundles with
the SMART launcher's default backend, seed the open `https://r4.smarthealthit.org`
endpoint from that clean shell, then use the returned ServiceRequest ids in the
SMART-enabled app. Public sandbox contents may be wiped.

## Idempotency and recovery

The review id is SHA-256 of canonical **complete reviewed JSON plus destination**.
A retry always loads and verifies the same saved artifact. It cannot replace the
payload under that id or redirect it to a different FHIR base. Mock artifacts,
unreviewed packets, invalid output contracts, and provenance with zero/multiple
ServiceRequests are rejected before a write.

The Task identifier uses system
`https://github.com/NickLeko/FHIR-Referral-Intake-Review/review-event` and the review
id as value. Before sending, the client requires advertised conditional-create
and identifier-search support, and searches for that exact identifier. Creation
uses `POST /Task` with **`If-None-Exist: identifier=<encoded-system|review-id>`**.
There is no unconditional POST fallback and no update of a conflicting Task.
This relies on server atomic conditional-create semantics, including concurrent
requests; a client-only hash cannot enforce uniqueness on a nonconforming server.

A post-send identifier search verifies the expected Task contents and unique
resource id, including after retry exhaustion. A 2xx response alone is not a
delivery receipt. Missing, conflicting, multiple, malformed or paginated matches
require human follow-up. A temporarily invisible write remains uncertain. A
crash after the server commits leaves a persisted uncertain row; replay searches
first and can acknowledge it without sending another POST. Delivered rows are
skipped on replay. Deleting history/outbox data or generating a fresh review to
"retry" discards these protections.

Inspect and explicitly replay saved reviews:

```bash
python -m src.deliver_reviews
python -m src.deliver_reviews --review-id SAVED_REVIEW_ID
python -m src.deliver_reviews --review-id ID1 --review-id ID2
python -m src.deliver_reviews --retry-pending
```

The last command retries undelivered reviews for the configured server only.
It does not generate a new review or change its timestamp. Commands return
nonzero when any requested delivery remains unresolved. In a partial batch,
successful writes remain successful; there is no rollback, all-or-nothing claim,
or automatic compensating clinical/administrative action.

## Failure semantics

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**

Default transport budget: initial attempt plus **two** transient retries, a
10-second request timeout, and exponential delays of 0.25 then 0.5 seconds.
A separate single 401 recovery permits at most one additional request. All
network attempts are synchronous and bounded; retries do not bypass review.

| Condition | System behavior | Human boundary / recovery |
| --- | --- | --- |
| 500 or transport interruption mid-read batch | Retry that request within budget. Exhaustion fails that packet closed; other referrals can proceed. Failed support fetches also abort that packet, rather than appearing as absent clinical data. | No packet or decision generated for the failed item. Inspect failure and re-fetch after recovery. Genuine 404/malformed references retain the prior missing/ambiguity rules. |
| Token expires between read and write | Reacquire before expiry; an unexpected 401 invalidates the token and reacquires once. Retry the identical conditional create. | Repeated 401, invalid grant, invalid token shape or missing scopes blocks access; no anonymous fallback. Saved review remains available. |
| Write commits but response is lost | Retry the same conditional create; search the exact identifier and verify content. | Mark delivered only when verified. Otherwise preserve `uncertain`; inspect and replay the same saved event after recovery. |
| 429 / Retry-After | Honor numeric seconds or HTTP date, combined with exponential backoff. If delay exceeds the 5-second synchronous cap, defer instead of shortening it. Exhausted 429 retries also establish a cooldown. | Outbox persists a server cooldown across restart and suppresses other batch writes until it ends. No unbounded worker loop; human initiates replay. Read-only CLI cooldown lasts for that client process. |
| Invalid Bundle/resource shape | Do not retry schema errors. Require a searchset Bundle with correctly shaped entries/links; validate resource identity and the existing single-ServiceRequest parser boundary. | No affected packet/write proceeds. Malformed post-write reconciliation remains uncertain. This is boundary validation, not full FHIR schema/profile validation. |
| Partial write batch / 500 mid-write batch | Track each event independently. Conditional creates get bounded retries and reconciliation. Continue unrelated events except during a shared rate-limit cooldown. | Landed writes are retained and skipped on replay. Failed/unknown events stay visible for investigation; the batch is never reported wholly successful. |
| Unsupported capability, identifier conflict or wrong destination | Fail closed, with no plain create or overwrite fallback. | Human fixes the server/configuration or investigates the conflicting event. |

A post-send error is conservatively uncertain even when the final response is a
4xx: an earlier transport attempt might have committed. A lookup failure before
any write is `needs_attention`. The local final status is never rewritten into a
delivery-error status.

## Verification and remaining limitations

The latest live verification **succeeded at 2026-09-08 04:09 UTC (2026-09-07
21:09 PDT)**. Screening checked **2 candidates**: **1** had a dangling Patient (410)
and the next, `ServiceRequest/REDACTED-ServiceRequest-02`, had a fully resolvable supported chain.
After Nick Leko explicitly confirmed `INCOMPLETE`, token acquisition returned 200
with an exact requested/granted scope match including `system/Task.crs`. The first
conditional Task POST returned **201**, id **REDACTED-Task-01**; GET by id returned **200**
with every submitted field matching. Repeated conditional POST returned **200**,
the **same id/version 1**, and identifier search returned **200**, `total: 1`.
Sandbox identifiers here are stable post-capture pseudonyms. No extensions were sent or returned. See the [complete live round-trip evidence](live_task_round_trip.md).

The earlier attempt at 00:31 UTC and the retry's first candidate both exposed a
live **410 Gone** for a deleted Patient referenced by a still-readable
ServiceRequest. The system failed that assembly closed. This verifies the sandbox
resource-lifecycle risk that also motivates seeded-resource retention checks in
the realism sweep. See the [original failure record](live_sandbox_verification.md).

Earlier **2026-09-07** implementation notes report these checks against the public SMART Health IT R4 launcher (not independently rerun in the final pass; the retained round-trip HTTP capture does not prove all of them):

- Generated registration and RS384 token acquisition succeeded.
- Discovery advertised client credentials and its token endpoint matched setup.
- Authenticated ServiceRequest search and individual read succeeded.
- Deliberately invalid assertion signature was rejected with HTTP 401.
- Explicit invalidation and acquisition of a new token succeeded.
- Server advertised Task conditional create, create/search interactions, and
  identifier search.

Concurrent uniqueness has no mocked concurrency test and remains unverified.
Task persistence/read-back and sequential conditional-write idempotency are now
verified live for one explicitly human-reviewed event. Concurrent uniqueness,
expired-token timing between read/write, dropped write responses, injected
500/429 failures, and partial write batches were **not verified live**. The
stateful mocked HTTP tests cover the injected failure/recovery paths; Streamlit
AppTest covers mock and live-review UI paths against that mocked server. Tests
require no external credentials or network access.

This is an integration artifact, **not production-grade**. It has no authenticated
reviewer identity/RBAC, no signed approval artifact or tamper-proof audit, no key
rotation/KMS, no encryption/retention/backup policy for local data, no distributed
outbox worker or operational monitoring, no full FHIR/SMART conformance suite,
no clinical/terminology validation, and no production authorization or privacy
certification. The reviewer name is a label, not verified identity. Operators
with filesystem/code access are trusted and can forge a local review.

The source may change while a human reviews it: provenance records fetched
versions but there is no atomic source-version precondition or coherent snapshot
across reads. Concurrent human reviews and server deletion/reset need manual
reconciliation. The chosen sandbox's public registration and open underlying
backend cannot establish production access-control guarantees. Do not use this
artifact for patient care or autonomous operational decisions.
