# Reference-integrity report

Server: `https://launch.smarthealthit.org/v/r4/sim/REDACTED-REGISTRATION/fhir`

Started: 2026-09-08T20:52:42.403473+00:00 | Finished: 2026-09-08T20:52:58.583460+00:00

Requested: 100 ServiceRequest resources; sampled: **100**.
Sampling stop: `requested_sample_reached`; pages: 2; duplicate sources skipped: 0.

Distinct-target resolution (queried server state): **11/36 (30.56%)** distinct queried targets.

Occurrence resolution (downstream exposure): **22/272 (8.09%)**, based on those same **36 distinct targets**, with **236 cache hits**.
Repeated references inherit a target's cached outcome. The occurrence rate weights targets by how often this source sample references them; it is not a second independent measurement of server state.

Sources with at least one known broken reference: **82/100 (82.00%)**.
Sources with any resolution problem (including unknown outcomes): **82/100 (82.00%)**.

Reference occurrences: 282; unique target lookups: 36; cache hits: 236.
Canonical fields excluded: 8; inventory shape issues: 0.

## Outcome classes

| Outcome | Reference occurrences |
| --- | ---: |
| display_only | 2 |
| gone_410 | 248 |
| logical | 2 |
| not_found_404 | 2 |
| resolved_200 | 22 |
| resolved_contained | 6 |

## By target resource type

| Group | Distinct resolved / queried targets | Distinct broken HTTP targets | References | Occurrence resolved / attempted (same distinct targets) | Broken occurrences | Other errors |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `Patient` | 9/16 (56.25%) | 7 | 98 | 15/97 (15.46%) | 82 | 0 |
| `Practitioner` | 1/7 (14.29%) | 6 | 88 | 6/87 (6.90%) | 81 | 0 |
| `Encounter` | 0/3 (0.00%) | 3 | 78 | 0/78 (0.00%) | 78 | 0 |
| `ObservationDefinition` | 1/4 (25.00%) | 3 | 4 | 1/4 (25.00%) | 3 | 0 |
| `Condition` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `MedicationAdministration` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `MedicationRequest` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `HealthcareService` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |
| `Organization` | 0/0 (undefined) | 0 | 3 | 0/0 (undefined) | 0 | 0 |
| `PractitionerRole` | 0/0 (undefined) | 0 | 2 | 0/0 (undefined) | 0 | 0 |
| `Unknown` | 0/0 (undefined) | 0 | 2 | 0/0 (undefined) | 0 | 0 |

## By source field path

| Group | Distinct resolved / queried targets | Distinct broken HTTP targets | References | Occurrence resolved / attempted (same distinct targets) | Broken occurrences | Other errors |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `ServiceRequest.subject` | 9/16 (56.25%) | 7 | 98 | 15/97 (15.46%) | 82 | 0 |
| `ServiceRequest.requester` | 1/5 (20.00%) | 4 | 87 | 6/85 (7.06%) | 79 | 0 |
| `ServiceRequest.encounter` | 0/3 (0.00%) | 3 | 78 | 0/78 (0.00%) | 78 | 0 |
| `ServiceRequest.extension[].extension[].extension[].valueReference` | 1/4 (25.00%) | 3 | 4 | 1/4 (25.00%) | 3 | 0 |
| `ServiceRequest.basedOn[]` | 0/2 (0.00%) | 2 | 3 | 0/2 (0.00%) | 2 | 0 |
| `ServiceRequest.extension[].extension[].extension[].extension[].valueReference` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `ServiceRequest.performer[]` | 0/2 (0.00%) | 2 | 4 | 0/2 (0.00%) | 2 | 0 |
| `ServiceRequest.reasonReference[]` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `ServiceRequest.contained[].generalPractitioner[]` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |
| `ServiceRequest.contained[].managingOrganization` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |
| `ServiceRequest.contained[].organization` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |
| `ServiceRequest.contained[].practitioner` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |

## Sampling design

```json
{
  "pages": 2,
  "duplicates_skipped": 0,
  "complete": true,
  "stop_reason": "requested_sample_reached",
  "method": "sequential"
}
```

## Broken-target clustering

Largest groups of sources sharing exactly the same set of broken targets (up to ten; all groups in JSON). Pseudonyms are local to this report, not comparable ids across runs.

| Sources | Shared broken targets |
| ---: | --- |
| 76 | Encounter/REDACTED-01, Patient/REDACTED-12, Practitioner/REDACTED-03 |
| 1 | Condition/REDACTED-01, Encounter/REDACTED-02, MedicationAdministration/REDACTED-01, MedicationRequest/REDACTED-01, ObservationDefinition/REDACTED-01, Patient/REDACTED-14 |
| 1 | Condition/REDACTED-02, Encounter/REDACTED-03, MedicationAdministration/REDACTED-02, MedicationRequest/REDACTED-02, ObservationDefinition/REDACTED-03, ObservationDefinition/REDACTED-04, Patient/REDACTED-16 |
| 1 | Patient/REDACTED-01 |
| 1 | Patient/REDACTED-04, Practitioner/REDACTED-01 |
| 1 | Patient/REDACTED-13, Practitioner/REDACTED-04, Practitioner/REDACTED-05 |
| 1 | Patient/REDACTED-15, Practitioner/REDACTED-06, Practitioner/REDACTED-07 |

## References per sampled source

| Reference count | Sources |
| ---: | ---: |
| 0 | 2 |
| 1 | 9 |
| 2 | 8 |
| 3 | 78 |
| 7 | 2 |
| 9 | 1 |

## Measurement boundaries

- One public sandbox at one moment; this original sequential sample measures one contiguous returned cohort, not server-wide prevalence. Search order alone does not establish creation order or a common deletion batch.
- All ids are run-local pseudonyms. No raw payloads, display text, logical identifiers, or credential values are retained.
- Distinct-target resolution describes the queried target state. Occurrence resolution weights those same targets by reference frequency and includes cache reuse; it describes downstream exposure, not an independent server-state estimate.
- Known broken means 404, 410 or missing contained target. Errors and blocked/unattempted refs are reported separately; known-broken source fraction is a lower bound when these exist.
- Logical and display-only references are not broken and are excluded from HTTP denominators. Contained targets are checked locally, never reported as HTTP 200.
- All standard R4 Reference fields in sampled JSON are walked, including extensions and contained resources. Canonical fields are counted separately, not dereferenced. Resolved targets are not recursively crawled.
- Out-of-server or unsafe URLs are not followed. Auth scopes are unchanged. Rate-limit deferral or auth failure halts new lookups; no anonymous fallback.
- A successful GET proves readability and identity at lookup time, not semantic consistency or a coherent snapshot. Cache entries, including failures, last for this run only.
- Clustering and distinct-target summaries were derived offline from the captured pseudonymized rows. Source/target outcomes and original run timestamps are unchanged. Pseudonyms cannot be compared across different runs.
