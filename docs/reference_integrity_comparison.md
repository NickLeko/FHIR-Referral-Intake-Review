# Reference integrity: contiguous versus scattered samples

**Distinct-target resolution was 11/36 (30.56%) in the original cohort and
10/116 (8.62%) in the scattered sample.** These describe the state of the
queried targets. The occurrence rates below describe downstream exposure to
those same targets, weighted by how many references reuse each result.

Server: SMART Health IT,
`https://launch.smarthealthit.org/v/r4/sim/REDACTED-REGISTRATION/fhir`.
Both measurements were live read-only runs on **2026-09-08 UTC**. No mock
responses were substituted. Reports were pseudonymized before publication.

## Direct comparison

| Measure | Original contiguous cohort | Scattered reservoir sample |
| --- | ---: | ---: |
| Sampled ServiceRequests | 100 | 100 |
| Distinct queried targets | **36** | **116** |
| Distinct targets resolved 200 | **11/36 (30.56%)** | **10/116 (8.62%)** |
| Distinct targets gone 410 | 23 | 105 |
| Distinct targets not found 404 | 2 | 1 |
| Occurrence resolution, using the distinct targets above | **22/272 (8.09%), from 36 targets** | **17/291 (5.84%), from 116 targets** |
| Cache hits included in occurrence denominator | 236 | 175 |
| Occurrences gone 410 | 248 | 273 |
| Occurrences not found 404 | 2 | 1 |
| Sources with at least one known broken reference | 82/100 (82%) | 95/100 (95%) |
| Sources with any resolution problem | 82/100 (82%) | 96/100 (96%) |
| All Reference occurrences | 282 | 294 |
| Display-only / logical | 2 / 2 | 1 / 0 |
| Locally resolved contained references | 6 | 0 |
| External/unsafe references blocked, excluded from HTTP denominator | 0 | 2 |
| Canonical fields excluded | 8 | 26 |
| Inventory issues / auth or rate-limit halts | 0 / 0 | 0 / 0 |
| Largest set of sources sharing exactly the same broken targets | 76 | 11 |

**Caching explains the different denominators:** in the original sample,
36 lookups plus 236 cached occurrences account for 272 HTTP-reference outcomes;
in the scattered sample, 116 lookups plus 175 cached occurrences account for
291. These are not 272 or 291 independent server probes. Logical/display-only,
contained, and blocked references are separate from HTTP resolution rates.
The second sample's 95% known-broken source fraction is a lower bound because
external targets were not resolved; one additional source had an external
resolution problem without an observed missing target.

## How the second sample avoids an adjacent cohort

The first run stopped after the first 100 unique ServiceRequests across two
pages, at 20:52:42–20:52:58 UTC. This measures one contiguous returned cohort;
search order alone does not prove consecutive creation or a single seed batch.

The second run, at 21:11:13–21:13:36 UTC, used **Algorithm R reservoir sampling,
seed 20260908**, while following the sandbox's next-page links. It scanned the
entire returned search stream: **8,831 unique sources across 177 pages**, zero
duplicates. It excluded the first 100 records of that current stream and
selected 100 uniformly from the remaining **8,731 eligible records**. The
10,000-source cap was not reached; the server exhausted its pages normally.
Only the selected sources' references were resolved.

Selected positions span **130–8,825**, with **zero adjacent selected pairs**.
The JSON preserves every selected position and the sampling parameters, without
resource ids. This spreads the selection across the available stream instead
of choosing another contiguous page. The normal search did not provide a
usable total through the existing client; reservoir sampling required none.
The fixed seed makes selection reproducible for an identical ordered stream,
not for a sandbox whose records or ordering have changed.

```bash
source .env.smart
python -m src.reference_integrity --resource-type ServiceRequest --sample-size 100 \
  --sampling reservoir --skip 100 --seed 20260908 --max-scan 10000 \
  --output-dir outputs/integration/reference-integrity-scattered
```

## The cross-type pattern is clustered

In the first sample, the apparently similar Patient, Practitioner, and Encounter
broken occurrence counts (**82/81/78**) represented only **7/6/3 distinct broken
targets**. Exactly **76 sources shared one deleted trio**:
`Patient/REDACTED-12`, `Practitioner/REDACTED-03`, and `Encounter/REDACTED-01`
in the original report's alias mapping. That trio accounts for **228/250
broken occurrences (91.2%)**. This is strong reference clustering, not three
independently demonstrated resource-type failure patterns.

The second sample reached **34/23/20 distinct broken Patient, Practitioner, and
Encounter targets**, accounting for **93/75/77 broken occurrences**. Its largest
exact shared broken-target set involved **11 sources**, followed by groups of
9, 9, 8, and 7. The failure therefore persists across many more target identities
and multiple reference clusters, beyond the first cohort's dominant trio.
Pseudonyms are local to each report: matching alias strings across files do not
establish that the underlying target was the same.

| Target resource type | Original distinct broken targets | Scattered distinct broken targets |
| --- | ---: | ---: |
| CarePlan | 0 | 5 |
| Condition | 2 | 10 |
| DiagnosticReport | 0 | 1 |
| DocumentReference | 0 | 2 |
| Encounter | 3 | 20 |
| Goal | 0 | 1 |
| MedicationAdministration | 2 | 0 |
| MedicationRequest | 2 | 0 |
| Observation | 0 | 2 |
| ObservationDefinition | 3 | 0 |
| Organization | 0 | 3 |
| Patient | 7 | 34 |
| Practitioner | 6 | 23 |
| Questionnaire | 0 | 5 |
| **Total** | **25** | **106** |

## Revised conclusion and limits

The first headline overstated the breadth of its evidence: 8.09% occurrence
resolution came from only **36 distinct targets**, whose actual distinct-target
resolution was **30.56%**. Its consumer impact was dominated by one shared trio.
After scattering the sources, distinct-target resolution was lower still:
**8.62% across 116 targets**, and known-broken source prevalence rose from
82% to 95%. The original clustering does not explain away the failure. The
follow-up supports a broader problem across the accessible ServiceRequest
search population, involving multiple overlapping reference clusters.

It does **not** establish that Patient, Practitioner, and Encounter fail through
independent mechanisms, nor does it prove a common cleanup or seeding batch.
It does not estimate the state of every resource type or every target on the
server: target inclusion depends on references from sampled ServiceRequests.
The samples were taken about 18 minutes apart on a mutable sandbox, without a
coherent snapshot. Because original raw ids were not retained, overlap between
the earlier sample and the later stream cannot be certified; skipping 100 means
current search positions. Timing and source selection cannot be disentangled
completely. These measurements are about one public sandbox, not production
FHIR servers or real patient-care workflows.

## Records and verification

- [Original report](reference_integrity_live_2026-09-08.md) and
  [per-reference JSON](reference_integrity_live_2026-09-08.json).
- [Scattered report](reference_integrity_scattered_2026-09-08.md) and
  [per-reference JSON](reference_integrity_scattered_2026-09-08.json).
- [Validator methodology and failure semantics](reference_integrity.md).

Source/target ids and registration paths are pseudonymized; payloads, display
text, logical identifiers, and credentials are omitted. The original outcomes
and timestamps were preserved; clustering and updated presentation were
computed offline from its captured rows. The second report records a new live
run. Injected 500s, rate-limit backoff/deferral, malformed payloads, and partial
sampling remain mock-tested. No Task writes or concurrency tests occurred in
these measurement runs.
