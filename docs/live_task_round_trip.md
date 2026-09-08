# Verified live SMART Health IT Task round trip

**Result: passed against the real public sandbox.** No mock server or simulated
reviewer was used. Nick Leko explicitly confirmed `INCOMPLETE` for the displayed
live packet before any Task write.

Reference screening occurred at **2026-09-08 00:48 UTC**. The reviewed write and
read-back occurred at **2026-09-08 04:09:02–04:09:03 UTC**
(**2026-09-07 21:09 PDT**), after the human confirmation arrived.
The implementation under test was `b74ad46` on `codex/fhir-auth-writeback`.

Identifiers were pseudonymized post-capture: Patient, ServiceRequest, Task, other resource ids, identifier-search values, and registration use stable aliases across the evidence and docs. `Task/REDACTED-Task-01` denotes the one actual created Task, not a second run. HTTP statuses, version 1, timestamps, counts, and comparisons retain their observed values.

## Candidate selection and lifecycle finding

Searched one ServiceRequest page, checked **2 candidates**, rejected **1** for a
dangling reference, and selected the second. There were **0 other rejections**.
The search stopped on that first eligible candidate; these counts do not estimate
failure prevalence across the whole sandbox.

| Candidate | Root read | Patient preflight | Result |
| --- | --- | --- | --- |
| `ServiceRequest/REDACTED-ServiceRequest-01` | 200 | `Patient/REDACTED-01`: **410 Gone** | Rejected: server reports Patient deleted |
| `ServiceRequest/REDACTED-ServiceRequest-02` | 200 | `Patient/REDACTED-02`: **200** | Selected |

Each Patient was checked before assembly. The selected referral contained no
other forward references in the existing supported assembly fields (`requester`,
`encounter`, `reasonReference`, `supportingInfo`). The assembler consumed only
those verified live responses and reported no reference-resolution issues. This
is the full **supported intake chain**, not a claim of recursively validating
all possible FHIR relationships or expanding the parser subset.

Its packet was still `INCOMPLETE`: Basic metabolic panel, routine priority,
missing referral reason, ordering provider, encounter context, and supporting
diagnosis. Resolvable references do not imply intake readiness. The human
confirmed incompleteness, and the Task records that disposition.

The first candidate reproduces the earlier live 410 observation. A ServiceRequest
can remain readable after its referenced Patient is deleted. This is the same
sandbox resource-lifecycle problem consistent with earlier observations of
seeded resources disappearing: retention is independent of referring resources. No
specific deletion actor or sandbox-wide cleanup event was established here.

## Actual HTTP results

All requests used the configured authenticated SMART launcher base. No alternate
open endpoint was used for verification, and each Task POST was a single HTTP
attempt without retrying a failure.

| Step | HTTP status | Returned id / observation |
| --- | --- | --- |
| Token acquisition | **200** | Requested and returned scopes exactly matched, including `system/Task.crs`; token TTL 600 seconds |
| First conditional `POST /Task` | **201 Created** | **`REDACTED-Task-01`**, `meta.versionId=1`, ETag `W/"1"` |
| `GET /Task/REDACTED-Task-01` | **200 OK** | **`REDACTED-Task-01`**, every submitted field matched |
| Same conditional `POST /Task`, identical body and identifier | **200 OK** | **`REDACTED-Task-01`**, still version 1 and ETag `W/"1"` |
| Identifier search after the repeat | **200 OK** | `total: 1`, exactly **`Task/REDACTED-Task-01`**, no next page |

Requested and explicitly granted scopes:

```text
system/Patient.rs system/ServiceRequest.rs system/Practitioner.rs system/Condition.rs system/Encounter.rs system/Observation.rs system/DocumentReference.rs system/Task.crs
```

Both writes used:

```http
POST $FHIR_BASE_URL/Task
Authorization: Bearer [REDACTED]
Accept: application/fhir+json
Content-Type: application/fhir+json
Prefer: return=representation
If-None-Exist: identifier=https%3A%2F%2Fgithub.com%2FNickLeko%2FFHIR-Referral-Intake-Review%2Freview-event%7CREDACTED-Identifier-05
```

Idempotency key: `REDACTED-Identifier-05`.

Both POST responses supplied
`Location: https://r4.smarthealthit.org/Task/REDACTED-Task-01/_history/1`.
The verifier used the returned body id to GET through the **configured SMART
base**, rather than following that Location to the open backend.

GET verification compared every submitted top-level field, including status,
identifier, focus, businessStatus, owner, note, output, and timestamps. The server
added `id` and `meta`. The persisted status was `completed`, the source reference
was `ServiceRequest/REDACTED-ServiceRequest-02`, and the human decision was `CONFIRM_INCOMPLETE` with
final disposition `INCOMPLETE`. Both `extension` and `modifierExtension` were
absent in the sent and returned resources; this does not test a nonempty extension.

The initial POST, GET, and repeated POST returned **identical response bodies**.
The same-id repeat plus the one-result identifier search verified no duplicate
for this sequential replay. It does not prove uniqueness under concurrent races.
The search entry itself contained historical `response.status: 201 Created`;
the repeated POST's actual HTTP status was **200**, as captured above.

## Sent Task and pseudonymized server representation

Request body, identical on both POSTs at capture, shown with identifier pseudonyms:

```json
{
  "resourceType": "Task",
  "identifier": [
    {
      "system": "https://github.com/NickLeko/FHIR-Referral-Intake-Review/review-event",
      "value": "REDACTED-Identifier-05"
    }
  ],
  "status": "completed",
  "intent": "order",
  "code": {
    "text": "Referral intake human review"
  },
  "businessStatus": {
    "text": "INCOMPLETE"
  },
  "focus": {
    "reference": "ServiceRequest/REDACTED-ServiceRequest-02"
  },
  "authoredOn": "2026-09-08T04:09:02.079904+00:00",
  "lastModified": "2026-09-08T04:09:02.079904+00:00",
  "owner": {
    "display": "Nick Leko"
  },
  "note": [
    {
      "authorString": "Nick Leko",
      "time": "2026-09-08T04:09:02.079904+00:00",
      "text": "Confirmed incomplete: referral reason, ordering provider, encounter context, and supporting diagnosis are missing."
    }
  ],
  "output": [
    {
      "type": {
        "text": "Human review decision"
      },
      "valueString": "CONFIRM_INCOMPLETE"
    },
    {
      "type": {
        "text": "Initial packet status"
      },
      "valueString": "INCOMPLETE"
    },
    {
      "type": {
        "text": "Next administrative step"
      },
      "valueString": "Request the missing intake elements before downstream administrative work."
    }
  ]
}
```

Response body returned by the first POST (**201**), GET (**200**), and
repeated conditional POST (**200**), with identifiers pseudonymized post-capture:

```json
{
  "resourceType": "Task",
  "id": "REDACTED-Task-01",
  "meta": {
    "versionId": "1",
    "lastUpdated": "2026-09-08T00:09:02.867-04:00"
  },
  "identifier": [
    {
      "system": "https://github.com/NickLeko/FHIR-Referral-Intake-Review/review-event",
      "value": "REDACTED-Identifier-05"
    }
  ],
  "status": "completed",
  "businessStatus": {
    "text": "INCOMPLETE"
  },
  "intent": "order",
  "code": {
    "text": "Referral intake human review"
  },
  "focus": {
    "reference": "ServiceRequest/REDACTED-ServiceRequest-02"
  },
  "authoredOn": "2026-09-08T04:09:02.079904+00:00",
  "lastModified": "2026-09-08T04:09:02.079904+00:00",
  "owner": {
    "display": "Nick Leko"
  },
  "note": [
    {
      "authorString": "Nick Leko",
      "time": "2026-09-08T04:09:02.079904+00:00",
      "text": "Confirmed incomplete: referral reason, ordering provider, encounter context, and supporting diagnosis are missing."
    }
  ],
  "output": [
    {
      "type": {
        "text": "Human review decision"
      },
      "valueString": "CONFIRM_INCOMPLETE"
    },
    {
      "type": {
        "text": "Initial packet status"
      },
      "valueString": "INCOMPLETE"
    },
    {
      "type": {
        "text": "Next administrative step"
      },
      "valueString": "Request the missing intake elements before downstream administrative work."
    }
  ]
}
```

## Durable evidence and limits

The original reviewed-output contract was preserved in the operational local JSON artifact
under `outputs/review_history/live/<review-id>.json`. Its original filename and payload remain local and gitignored; pseudonymized evidence is not a delivery/replay input.
The SQLite outbox receipt is `delivered`; its Task reference is shown here with a post-capture pseudonym: `Task/REDACTED-Task-01`.

Local, gitignored evidence under `outputs/integration/live-verification-retry/`:

- `candidate-results.json`: candidate counts and each reference/status check.
- `preparation-http.json`: actual screening HTTP exchanges.
- `human-approval.json`: source, reviewer, exact user confirmation and timestamp.
- `task-sent.json`: captured Task payload with post-capture identifier pseudonyms.
- `write-http.json`: complete actual request URLs, headers and bodies, plus full
  response headers/bodies. Tokens and signed assertions are redacted; record ids, identifier values and registration are pseudonymized. Each JSON includes a `redaction_note`. Historical Content-Length describes the captured bytes, not the edited body length.
- `write-result.json`: actual step statuses, ids, field comparisons and count.

The earlier 410 failure record remains in `docs/live_sandbox_verification.md`.
No resource deletion or cleanup was performed after this successful verification.
Public sandbox resource retention is not guaranteed.

**Still mock-tested only:** committed-but-lost write responses, deliberately
injected 500/429 responses, token expiration between read and write, and partial
write batches. This live run establishes a human-reviewed Task round trip and
sequential conditional-create idempotency, not production security, source
snapshot consistency, authenticated reviewer identity, or concurrent uniqueness.

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**
