# Reference-integrity report

Server: `https://launch.smarthealthit.org/v/r4/sim/REDACTED-REGISTRATION/fhir`

Started: 2026-09-08T21:11:13.229923+00:00 | Finished: 2026-09-08T21:13:36.004077+00:00

Requested: 100 ServiceRequest resources; sampled: **100**.
Sampling stop: `server_exhausted`; pages: 177; duplicate sources skipped: 0.

Distinct-target resolution (queried server state): **10/116 (8.62%)** distinct queried targets.

Occurrence resolution (downstream exposure): **17/291 (5.84%)**, based on those same **116 distinct targets**, with **175 cache hits**.
Repeated references inherit a target's cached outcome. The occurrence rate weights targets by how often this source sample references them; it is not a second independent measurement of server state.

Sources with at least one known broken reference: **95/100 (95.00%)**.
Sources with any resolution problem (including unknown outcomes): **96/100 (96.00%)**.

Reference occurrences: 294; unique target lookups: 116; cache hits: 175.
Canonical fields excluded: 26; inventory shape issues: 0.

## Outcome classes

| Outcome | Reference occurrences |
| --- | ---: |
| display_only | 1 |
| gone_410 | 273 |
| not_found_404 | 1 |
| resolved_200 | 17 |
| unresolvable_external_or_unsafe | 2 |

## By target resource type

| Group | Distinct resolved / queried targets | Distinct broken HTTP targets | References | Occurrence resolved / attempted (same distinct targets) | Broken occurrences | Other errors |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `Patient` | 5/39 (12.82%) | 34 | 101 | 7/100 (7.00%) | 93 | 0 |
| `Practitioner` | 2/25 (8.00%) | 23 | 82 | 7/82 (8.54%) | 75 | 0 |
| `Encounter` | 0/20 (0.00%) | 20 | 77 | 0/77 (0.00%) | 77 | 0 |
| `Condition` | 0/10 (0.00%) | 10 | 10 | 0/10 (0.00%) | 10 | 0 |
| `CarePlan` | 0/5 (0.00%) | 5 | 5 | 0/5 (0.00%) | 5 | 0 |
| `Questionnaire` | 0/5 (0.00%) | 5 | 6 | 0/5 (0.00%) | 5 | 0 |
| `Organization` | 0/3 (0.00%) | 3 | 3 | 0/3 (0.00%) | 3 | 0 |
| `DocumentReference` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `Observation` | 0/2 (0.00%) | 2 | 2 | 0/2 (0.00%) | 2 | 0 |
| `DiagnosticReport` | 0/1 (0.00%) | 1 | 1 | 0/1 (0.00%) | 1 | 0 |
| `Goal` | 0/1 (0.00%) | 1 | 1 | 0/1 (0.00%) | 1 | 0 |
| `Consent` | 1/1 (100.00%) | 0 | 1 | 1/1 (100.00%) | 0 | 0 |
| `Coverage` | 1/1 (100.00%) | 0 | 1 | 1/1 (100.00%) | 0 | 0 |
| `Specimen` | 1/1 (100.00%) | 0 | 1 | 1/1 (100.00%) | 0 | 0 |
| `Unknown` | 0/0 (undefined) | 0 | 1 | 0/0 (undefined) | 0 | 0 |

## By source field path

| Group | Distinct resolved / queried targets | Distinct broken HTTP targets | References | Occurrence resolved / attempted (same distinct targets) | Broken occurrences | Other errors |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `ServiceRequest.subject` | 5/39 (12.82%) | 34 | 100 | 6/99 (6.06%) | 93 | 0 |
| `ServiceRequest.encounter` | 0/20 (0.00%) | 20 | 77 | 0/77 (0.00%) | 77 | 0 |
| `ServiceRequest.requester` | 3/22 (13.64%) | 19 | 79 | 8/78 (10.26%) | 70 | 0 |
| `ServiceRequest.reasonReference[]` | 0/13 (0.00%) | 13 | 13 | 0/13 (0.00%) | 13 | 0 |
| `ServiceRequest.extension[].extension[].valueReference` | 0/7 (0.00%) | 7 | 7 | 0/7 (0.00%) | 7 | 0 |
| `ServiceRequest.basedOn[]` | 0/5 (0.00%) | 5 | 5 | 0/5 (0.00%) | 5 | 0 |
| `ServiceRequest.modifierExtension[].valueReference` | 0/5 (0.00%) | 5 | 6 | 0/5 (0.00%) | 5 | 0 |
| `ServiceRequest.supportingInfo[]` | 1/3 (33.33%) | 2 | 3 | 1/3 (33.33%) | 2 | 0 |
| `ServiceRequest.extension[].valueReference` | 0/1 (0.00%) | 1 | 1 | 0/1 (0.00%) | 1 | 0 |
| `ServiceRequest.performer[]` | 0/1 (0.00%) | 1 | 1 | 0/1 (0.00%) | 1 | 0 |
| `ServiceRequest.insurance[]` | 1/1 (100.00%) | 0 | 1 | 1/1 (100.00%) | 0 | 0 |
| `ServiceRequest.specimen[]` | 1/1 (100.00%) | 0 | 1 | 1/1 (100.00%) | 0 | 0 |

## Sampling design

```json
{
  "method": "reservoir",
  "skip_requested": 100,
  "random_seed": 20260908,
  "scan_limit": 10000,
  "scanned_unique_sources": 8831,
  "eligible_sources": 8731,
  "population_exhausted": true,
  "pages": 177,
  "duplicates_skipped": 0,
  "complete": true,
  "stop_reason": "server_exhausted",
  "selected_position_min_max": [
    130,
    8825
  ],
  "adjacent_selected_pairs": 0
}
```

## Broken-target clustering

Largest groups of sources sharing exactly the same set of broken targets (up to ten; all groups in JSON). Pseudonyms are local to this report, not comparable ids across runs.

| Sources | Shared broken targets |
| ---: | --- |
| 11 | Encounter/REDACTED-01, Patient/REDACTED-01, Practitioner/REDACTED-01 |
| 9 | Encounter/REDACTED-04, Patient/REDACTED-04, Practitioner/REDACTED-04 |
| 9 | Encounter/REDACTED-06, Patient/REDACTED-06, Practitioner/REDACTED-06 |
| 8 | Encounter/REDACTED-05, Patient/REDACTED-05, Practitioner/REDACTED-05 |
| 7 | Encounter/REDACTED-03, Patient/REDACTED-03, Practitioner/REDACTED-03 |
| 6 | Encounter/REDACTED-11, Patient/REDACTED-14, Practitioner/REDACTED-12 |
| 4 | Encounter/REDACTED-09, Patient/REDACTED-12, Practitioner/REDACTED-09 |
| 3 | Encounter/REDACTED-13, Patient/REDACTED-16, Practitioner/REDACTED-16 |
| 2 | Encounter/REDACTED-11, Patient/REDACTED-14, Practitioner/REDACTED-13 |
| 2 | Encounter/REDACTED-12, Patient/REDACTED-15, Practitioner/REDACTED-14 |

## References per sampled source

| Reference count | Sources |
| ---: | ---: |
| 1 | 4 |
| 2 | 11 |
| 3 | 82 |
| 4 | 2 |
| 14 | 1 |

## Measurement boundaries

- One public sandbox at one moment. Sequential sampling measures a contiguous returned cohort; reservoir sampling covers only its documented eligible stream, not production prevalence.
- All ids are run-local pseudonyms. No raw payloads, display text, logical identifiers, or credential values are retained.
- Distinct-target resolution describes queried target state. Occurrence resolution describes downstream exposure to those same targets, including cached outcomes; it is not an independent server-state estimate. Transport retries may add HTTP requests.
- Known broken means 404, 410 or missing contained target. Errors and blocked/unattempted refs are reported separately; known-broken source fraction is a lower bound when these exist.
- Logical and display-only references are not broken and are excluded from HTTP denominators. Contained targets are checked locally, never reported as HTTP 200.
- All standard R4 Reference fields in sampled JSON are walked, including extensions and contained resources. Canonical fields are counted separately, not dereferenced. Resolved targets are not recursively crawled.
- Out-of-server or unsafe URLs are not followed. Auth scopes are unchanged. Rate-limit deferral or auth failure halts new lookups; no anonymous fallback.
- A successful GET proves readability and identity at lookup time, not semantic consistency or a coherent snapshot. Cache entries, including failures, last for this run only.
