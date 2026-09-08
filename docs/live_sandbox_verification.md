# SMART Health IT live write-back verification attempt

**Historical first attempt.** A later retry succeeded: **201 → 200 → 200**,
`Task/REDACTED-Task-01`, with one identifier match. See [the successful live round trip](live_task_round_trip.md).
The failure below remains a verified live observation.

Run time: **2026-09-08 00:31:19–00:31:20 UTC**
(**2026-09-07 17:31:19–17:31:20 America/Los_Angeles**).
Implementation under test: `codex/fhir-auth-writeback`, commit `b74ad46`.

**Result: stopped during source assembly, before a completed human review or any
Task POST. The round trip did not complete. This was not a Task rejection.**

The operator requested stopping at the first failure. No alternate referral,
mock server, fallback endpoint, or simulated reviewer decision was used after
that failure. This attempt used the existing `.env.smart` registration and the
real public SMART Health IT endpoint, with transient retries disabled.

Identifiers were pseudonymized post-capture, consistently with the retry evidence; HTTP statuses and the 410 response body are unchanged.

## Actual sequence

| Request / verification | Observed result |
| --- | --- |
| POST configured `/auth/token` with `grant_type=client_credentials` and RS384 assertion | HTTP **200**; Bearer token with `expires_in=600` |
| Compare requested scopes against token response `scope` | Exact set equality; all eight scopes returned, including **`system/Task.crs`**; no missing scopes |
| GET `$FHIR_BASE_URL/ServiceRequest?_count=1` to select a live source | HTTP **200**; returned `ServiceRequest/REDACTED-ServiceRequest-01` |
| GET `$FHIR_BASE_URL/ServiceRequest/REDACTED-ServiceRequest-01` | HTTP **200**; source references `Patient/REDACTED-01` |
| GET `$FHIR_BASE_URL/Patient/REDACTED-01` during normal narrow reference assembly | HTTP **410 Gone**, with the complete body below; assembly aborted |
| Complete human review and POST Task | **Not reached / no Task request sent** |
| GET created Task by id and compare status, source reference, reviewer disposition, extensions | **Not reached; no Task id exists for this attempt** |
| Repeat conditional POST with the same idempotency key | **Not reached; no 200/201 or same/new-id observation is available** |

No completed live human review was present locally when the run began. The
checked-in reviewed outputs are generated mock fixtures; relabeling one as a
completed live human review would not satisfy the human gate. The source fetch
was necessary to prepare a live packet for an actual reviewer. Its failure
prevented that prerequisite from completing.

## Requested versus granted scopes

The following exact string was requested and explicitly returned in the token
response. No scope was assumed from an omitted `scope` field:

```text
system/Patient.rs system/ServiceRequest.rs system/Practitioner.rs system/Condition.rs system/Encounter.rs system/Observation.rs system/DocumentReference.rs system/Task.crs
```

Token response body (only the access credential is redacted):

```json
{"access_token":"[REDACTED credential]","token_type":"Bearer","expires_in":600,"scope":"system/Patient.rs system/ServiceRequest.rs system/Practitioner.rs system/Condition.rs system/Encounter.rs system/Observation.rs system/DocumentReference.rs system/Task.crs"}
```

A granted create scope is evidence of token negotiation. It is not evidence that
a Task POST is accepted, persisted, or made unique by this server.

## Exact failure

The request used the configured registered base
`https://launch.smarthealthit.org/v/r4/sim/<registration>/fhir`:

```http
GET $FHIR_BASE_URL/Patient/REDACTED-01
User-Agent: FHIR-Referral-Intake-Review/1.0
Accept-Encoding: gzip, deflate
Accept: application/fhir+json
Connection: keep-alive
Authorization: Bearer [REDACTED]
```

There was no request body. `$FHIR_BASE_URL` above abbreviates the lengthy
registration URL; the captured URL and every request/response header are
retained with record identifiers and registration pseudonymized in the local evidence file described below.

The server returned HTTP **410**, with
`Content-Type: application/fhir+json;charset=utf-8`, `Content-Length: 202`, and
`Date: Tue, 08 Sep 2026 00:31:20 GMT`. Its **complete, unmodified response body** was:

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "error",
      "code": "processing",
      "diagnostics": "Resource was deleted at 2026-09-02T03:02:13.718-04:00"
    }
  ]
}
```

**Diagnosis:** the retrieved ServiceRequest points at a Patient that the server
reports as deleted. This is a dangling source reference in mutable public
sandbox data. The immediate cause of this run's failure is that 410 response,
not a rejected write scope or invalid Task payload. The assembler tolerates
404/unsafe references as data-quality issues, but propagates 410 as
`FHIRHTTPError` and fails this assembly closed. Its behavior was not changed to
force a successful demonstration. The evidence does not establish who deleted
the resource or why.

## Evidence and verification limits

The local, gitignored file
`outputs/integration/live-verification/preparation-http.json` contains all four
actual HTTP exchanges: full request URLs/headers/bodies and full response
headers/bodies. Bearer tokens and signed client assertions are redacted; resource ids, identifier values, and registration were also pseudonymized post-capture. No response was replaced by a mock. The final failure response is
unmodified. Registration configuration and raw public-sandbox source data are
kept out of the committed documentation. Evidence JSON includes a `redaction_note`; it is not replayable wire data.

`outputs/integration/live-verification/preparation-result.json` records the
stopped result. The local `prepare.py` records requests using a real
`requests.Session`; it is not a mock server and makes no Task writes.

This run verifies token acquisition with an explicitly granted create scope,
authenticated referral search/read, and actual fail-closed behavior for a deleted
support resource. The prior 2026-09-07 checks of renewal, invalid-signature
rejection, and advertised Task capabilities remain historical observations;
those checks were not repeated after this run failed.

**At the end of this first attempt, still only mock-tested:** Task POST acceptance, Task persistence/read-back,
conditional-create duplicate prevention, committed-but-lost responses, injected
500/429 failures, expired-token timing between read/write, and partial write
batches. No actual Task id, Task POST response, or live idempotency result can be
reported for this attempt. The later retry found a resolvable source packet, obtained a completed human
review, and verified the POST/GET/repeated-POST sequence in the linked report.

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**
