# FHIR Sandbox Realism Sweep

Generated: 2026-09-04T04:40:40+00:00

Historical live HAPI findings retained from the pre-existing sweep; the integration pass did not rerun this sample. The six offline sweep tests validate aggregation/reporting behavior, not the historical server contents. The separate SMART round trip and 410 observation are documented in [the README failure semantics](../README.md#failure-semantics).

This report contains aggregate review findings only. Raw server resources, resource IDs, and patient-level values are not retained.

The public HAPI sandbox is periodically wiped, so its contents and returned resource IDs are not stable.

## Scope

- Server base URL: `https://hapi.fhir.org/baseR4`
- Requested maximum found ServiceRequests: 50
- Found ServiceRequests discovered (known seeded resources excluded): 50
- Found ServiceRequests reviewed: 50
- Found ServiceRequests failing root assembly: 0

## Found-sample status distribution

| Status | Count | Percent of reviewed |
| --- | ---: | ---: |
| `REVIEW_READY` | 0 | 0.0% |
| `INCOMPLETE` | 50 | 100.0% |
| `HUMAN_CONFIRMATION_REQUIRED` | 0 | 0.0% |

## Seeded synthetic comparison

Previously seeded synthetic ServiceRequests are checked directly and are not included in the found public-sandbox sample. Their resource IDs are not shown.

- Seeded ServiceRequests checked: 7
- Seeded ServiceRequests still resolvable and reviewed: 7
- Seeded ServiceRequests not found: 0
- Other seeded root review failures: 0

### Seeded status distribution

| Status | Count | Percent of reviewed seeds |
| --- | ---: | ---: |
| `REVIEW_READY` | 2 | 28.6% |
| `INCOMPLETE` | 4 | 57.1% |
| `HUMAN_CONFIRMATION_REQUIRED` | 1 | 14.3% |

### Seeded missing elements

| Element or reason | Count |
| --- | ---: |
| `ordering_provider` | 2 |
| `supporting_diagnosis` | 2 |
| `encounter_context` | 1 |
| `patient_age_group` | 1 |

### Seeded ambiguous elements

| Element or reason | Count |
| --- | ---: |
| `ordering_provider` | 1 |
| `referral_reason` | 1 |
| `requested_service` | 1 |

### Seeded assembly failures

- Seeded ServiceRequests with one or more reference/resource assembly failures: 2

| Element or reason | Count |
| --- | ---: |
| `fetch_failed` | 1 |
| `invalid_reference` | 1 |

## Sparse-resource characterization

The parser expects 6 intake elements: `requested_service`, `referral_reason`, `ordering_provider`, `patient_age_group`, `encounter_context`, `supporting_diagnosis`. Presence means the parser produced a non-empty value; an ambiguous value still counts as present.

### Found public-sandbox sample

| Expected elements present | ServiceRequests | Percent of reviewed |
| --- | ---: | ---: |
| `0 of 6` | 0 | 0.0% |
| `1 of 6` | 27 | 54.0% |
| `2 of 6` | 14 | 28.0% |
| `3 of 6` | 6 | 12.0% |
| `4 of 6` | 1 | 2.0% |
| `5 of 6` | 2 | 4.0% |
| `6 of 6` | 0 | 0.0% |

### Seeded synthetic sample

| Expected elements present | ServiceRequests | Percent of reviewed |
| --- | ---: | ---: |
| `0 of 6` | 0 | 0.0% |
| `1 of 6` | 0 | 0.0% |
| `2 of 6` | 0 | 0.0% |
| `3 of 6` | 1 | 14.3% |
| `4 of 6` | 0 | 0.0% |
| `5 of 6` | 3 | 42.9% |
| `6 of 6` | 3 | 42.9% |

## Most common missing elements

| Element or reason | Count |
| --- | ---: |
| `supporting_diagnosis` | 50 |
| `encounter_context` | 46 |
| `ordering_provider` | 43 |
| `referral_reason` | 43 |
| `patient_age_group` | 30 |
| `requested_service` | 1 |

## Most common ambiguous elements

| Element or reason | Count |
| --- | ---: |
| `ordering_provider` | 3 |
| `referral_reason` | 2 |

## Assembly failures

An assembly failure means a referenced resource could not be safely resolved or a root ServiceRequest could not be reviewed.

- Found ServiceRequests with one or more reference/resource assembly failures: 29
- Total found-sample assembly failures: 29

| Element or reason | Count |
| --- | ---: |
| `invalid_reference` | 28 |
| `fetch_failed` | 1 |

## Search and pagination observations

None observed.

## Interpretation

The main result is the seeded-versus-found contrast through the identical parser and review code path: the realistic seeded bundles produced 2 `REVIEW_READY` / 4 `INCOMPLETE` / 1 `HUMAN_CONFIRMATION_REQUIRED`, while all 50 third-party found ServiceRequests were `INCOMPLETE`. The found sample's incomplete rate reflects sparse public-sandbox test resources—41 of 50 (82%) carried only one or two of the six expected elements, and none carried all six—not an estimate of real-world referral completeness.

The 28 `invalid_reference` observations are a workflow finding: unresolvable references on untrusted server data flowed into the existing missing-element detection rather than crashing the assembler or being silently dropped. That is the designed behavior, now validated against real malformed sandbox data rather than treated as a software failure.

Assembly issues rose from 1 of 10 resources in the earlier run to 29 of 50 in this run, and it is unclear whether the n=10 run drew a favorable sample or pagination reached a different region of the server.
