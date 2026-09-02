# FHIR Sandbox Realism Sweep

Generated: 2026-09-02T22:06:46+00:00

This report contains aggregate review findings only. Raw server resources, resource IDs, and patient-level values are not retained.

The public HAPI sandbox is periodically wiped, so its contents and returned resource IDs are not stable.

## Scope

- Server base URL: `https://hapi.fhir.org/baseR4`
- Requested maximum ServiceRequests: 10
- ServiceRequests discovered: 10
- ServiceRequests reviewed: 10
- ServiceRequests failing root assembly: 0

## Status distribution

| Status | Count | Percent of reviewed |
| --- | ---: | ---: |
| `REVIEW_READY` | 0 | 0.0% |
| `INCOMPLETE` | 10 | 100.0% |
| `HUMAN_CONFIRMATION_REQUIRED` | 0 | 0.0% |

## Most common missing elements

| Element or reason | Count |
| --- | ---: |
| `supporting_diagnosis` | 10 |
| `encounter_context` | 8 |
| `ordering_provider` | 8 |
| `referral_reason` | 7 |
| `patient_age_group` | 2 |
| `requested_service` | 1 |

## Most common ambiguous elements

None observed.

## Assembly failures

An assembly failure means a referenced resource could not be safely resolved or a root ServiceRequest could not be reviewed.

- ServiceRequests with one or more reference/resource assembly failures: 1
- Total assembly failures: 1

| Element or reason | Count |
| --- | ---: |
| `fetch_failed` | 1 |

## Search and pagination observations

None observed.

## Interpretation

These counts describe how the existing deterministic parser behaved on the sandbox sample. A high incomplete or confirmation-required rate is reported as a workflow finding, not treated as a software failure.
