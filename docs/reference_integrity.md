# Reference-integrity validator

This read-only diagnostic measures references in a sample of FHIR R4 resources.
It uses the existing `FHIRClient` and SMART Backend Services authentication,
token renewal, URL restrictions, response validation, and retry policy. It does
not assemble review packets, change a disposition, or write to the server.
The intake parser's seven resource types and single-ServiceRequest human review
gate are unchanged.

## Run it

From the repository root, with dependencies installed and an existing local
SMART registration loaded (see [integration setup](integration.md)):

```bash
source .env.smart
python -m src.reference_integrity --resource-type ServiceRequest --sample-size 100
```

The command writes pseudonymized `report.json` and `report.md` to
`outputs/integration/reference-integrity/`, which is ignored by Git. Use
`--output-dir` to choose a different directory. Subsequent runs replace these
two files. The JSON includes every reference occurrence and source record;
Markdown presents the aggregates. No fetched resource bodies are saved.

`--base-url` uses the existing client's configuration checks and must agree
with the configured SMART server. Without SMART configuration, the existing
open HAPI default applies. No authentication failure triggers anonymous fallback.
Resource types are the 146 standard R4 resource types; requested sample sizes
are 1–10,000. Server support and granted read permissions still govern access.
The validator does not broaden the configured SMART scopes automatically.

Search pages request at most 50 resources. The validator follows validated
`next` links, deduplicates source ids, and stops at the requested number or
server exhaustion. Cycles, ambiguous links, malformed pages, and a bounded
page budget stop sampling with an explicit reason. Reports retain the actual
number obtained; a partial sample is never presented as the requested size.
The default is the server's contiguous returned cohort. Search order does not
prove creation order or a common seeding event.

To scatter selection across subsequent pages, use fixed-seed reservoir sampling:

```bash
python -m src.reference_integrity --resource-type ServiceRequest --sample-size 100 \
  --sampling reservoir --skip 100 --seed 20260908 --max-scan 10000 \
  --output-dir outputs/integration/reference-integrity-scattered
```

Reservoir sampling gives each eligible unique source in the traversed stream
the same inclusion probability, using a deterministic pseudorandom generator.
It retains only the selected resource bodies while paging, deduplicates ids,
and excludes the first `--skip` unique records in the current search order.
Reports retain selected stream positions, the seed, scanned/eligible counts,
and whether the population was exhausted. `--max-scan` bounds source reads
(up to 100,000); reaching it before exhaustion returns exit 2 and limits the
sampling frame to that prefix. The next-page traversal does not need a server
total. It still is not a server-wide random sample of target resources: targets
are reached through the selected sources. Search authorization and changes
during pagination also limit what is observed. Skipping current positions does
not prove no overlap with an earlier snapshot whose raw ids were not retained.

## What is walked

The walker uses checked-in field/type metadata derived from the official
[HL7 FHIR R4 4.0.1 JSON schema](https://hl7.org/fhir/R4/fhir.schema.json.zip).
It follows standard `Reference` fields through nested structures, primitive
extensions, `Extension.valueReference`, and contained resources. A Coding's
`display` is not mistaken for a display-only Reference. Array indices are
retained in individual paths and normalized to `[]` for grouped statistics.

Contained `#id` references are checked in their containing resource locally;
they are not reported as HTTP 200. Canonical fields are a separate FHIR datatype
and are counted without dereferencing. Fetched targets are not recursively
crawled. URNs, including Bundle-local fullUrl URNs, are currently reported as
having no REST id; Bundle fullUrl resolution is not implemented. External or
unsafe URLs are recorded but not followed or given credentials.

This is not full FHIR or profile validation. It traverses known R4 fields, not
unknown nonstandard JSON fields. Invalid complex/array shapes and traversal
depth above 64 produce inventory issues. HTTP 200 also requires the existing
client's JSON/resource identity checks; a malformed 200 response is an error
with status 200, not a resolved target.

Metadata provenance, schema checksum, and CC0 attribution are in
`data/fhir_r4_reference_shapes.json`. To regenerate from a separately downloaded
official ZIP, run:

```bash
python scripts/build_reference_shapes.py /path/to/fhir.schema.json.zip
```

## Outcomes and denominators

| Outcome | Meaning |
| --- | --- |
| `resolved_200` | GET returned 200 and passed resource identity validation |
| `gone_410` | Server returned 410 |
| `not_found_404` | Server returned 404; this alone does not prove deletion |
| `other_error` | Other HTTP status or transport/auth/response-validation error; status is null if unavailable |
| `display_only`, `logical` | No literal reference; display text or a logical identifier is present. Logical takes precedence when both exist |
| `resolved_contained`, `missing_contained` | Local fragment target present or unavailable; no HTTP request |
| `unresolvable_invalid`, `unresolvable_type_mismatch` | Invalid Reference or declared type inconsistent with target type |
| `unresolvable_external_or_unsafe`, `unresolvable_no_rest_id` | Blocked URL or no supported REST identity, including URNs |
| `not_attempted` | New lookup skipped after an auth or rate-limit halt |

The headline rate is **resolved distinct targets / all distinct queried
targets**. It measures the state of those queried targets, not every resource
on the server. The second rate is successful HTTP reference occurrences divided
by attempted occurrences, **including cached outcomes**: downstream exposure
to the same targets, weighted by how often the source sample references them.
Its distinct-target denominator is shown alongside every occurrence rate.
These are two views of the same lookups, not independent server measurements.
Each target is fetched once per run,
apart from the existing transport's retries; absolute and relative references
to the same local target share a cache entry. Version-specific references have
separate entries. Failures are cached too. `lookup_attempted` means the client
resolver was invoked: authentication may fail before a FHIR GET is sent, and
transport retries may cause more than one HTTP request per lookup.

Display-only, logical, contained, blocked, and unattempted references are
excluded from HTTP denominators. A zero denominator yields an undefined rate,
not 0% success. The report separately counts all Reference occurrences.

The consumer measure is **sources with at least one known broken reference /
all sampled sources**, including sources with zero references. Known broken
means 404, 410, or a missing contained target. Logical/display-only references
are not failures. A separate source fraction includes other resolution problems
and inventory issues. When unknown outcomes exist, the known-broken fraction
is a lower bound. Breakdowns by target type and source field include counts and
resolution denominators, and the report includes the references-per-source
distribution.

## Failure behavior and verification boundary

The default pacing waits at least 0.25 seconds between completed client
operations; increase this with `--min-interval` (0–60 seconds). Existing bounded
transport retries use exponential backoff and honor Retry-After. A long or
exhausted rate-limit response defers the run: no new targets are fetched, while
cached outcomes remain usable. Persistent auth/authorization failure similarly
halts new resolution. Exhausted 500s are recorded per target; other targets can
continue. Sampling failures preserve resources already obtained. These are
measurement outcomes; they never authorize a review or delivery.

CLI exit 0 means sampling reached the requested size or exhausted the server
without a run/inventory halt; findings such as 404 and 410 do not make the CLI
fail. Exit 2 means sampling, inventory, or an auth/rate-limit halt limited the
run. Individual `other_error` outcomes can coexist with exit 0; inspect the
report. Exit 1 means configuration or local report writing failed.

The [2026-09-08 live reports](reference_integrity_comparison.md) verified
paginated reads, 200/404/410 outcomes, local contained resolution, nonliteral
reference classification, scattered reservoir selection, external-reference blocking,
and cache reuse against SMART Health IT. Injected
500s, 429 backoff/deferral, malformed responses, unsafe-reference variants, and partial
sampling are mock-tested; no injected failure was observed in these runs. This validator does no
write-back or idempotency testing. The earlier [Task round trip](live_task_round_trip.md)
verified token acquisition, conditional create, read-back, and sequential
replay live; concurrent uniqueness remains unverified.

## Live finding and privacy limits

The [direct comparison](reference_integrity_comparison.md) distinguishes target
state from downstream exposure. On **2026-09-08 UTC**, the first contiguous
100-source cohort resolved **11/36 distinct queried targets (30.56%)**. Its
occurrence resolution was **22/272 (8.09%) from those same 36 targets**, with
236 cache hits; 82/100 sources had a broken reference. Of 282 Reference
occurrences, 248 returned 410, two returned 404, six resolved locally, two were
display-only, and two were logical. Eight canonical fields were excluded.

The second run used the reservoir command above, exhausted **177 pages / 8,831
unique ServiceRequests**, skipped the first 100, and selected 100 from **8,731
eligible sources**. Selected positions ranged from **130 to 8,825**, with no
adjacent pairs. **10/116 distinct queried targets resolved (8.62%)**; downstream
occurrence resolution was **17/291 (5.84%) from those same 116 targets**, with
175 cache hits. **95/100** sources had a broken reference. Of 294 Reference
occurrences, 273 returned 410, one returned 404, one was display-only, and two
external/unsafe references were not attempted. There were no logical or
contained references; 26 canonical fields were excluded. Both runs had no
inventory issues or auth/transport halts. One additional second-sample source
had only an unresolved external reference, making the broader problem fraction
96/100 rather than the known-broken 95/100.

The first sample's Patient, Practitioner, and Encounter broken occurrences (82/81/78)
represented only **7/6/3 distinct broken targets**; **76 sources shared one
exact deleted trio**, accounting for 228 of 250 broken occurrences. The second
sample had **34/23/20 distinct broken targets** in those types; its largest
shared broken-target set involved **11 sources**. This is evidence of repeated
reference clusters and failure beyond the first cohort, not three independently
established resource-type failure mechanisms. It does not identify a seeding
batch, deletion actor, or cleanup policy.

The [first report](reference_integrity_live_2026-09-08.md) and
[second report](reference_integrity_scattered_2026-09-08.md) contain all field
breakdowns and source distributions; corresponding JSON files preserve every
pseudonymized reference row. The second sample is scattered across the
accessible ServiceRequest search results, but neither run estimates the state
of every resource on the server or production FHIR prevalence. Target lookups
are induced by source sampling, outcomes are cached, and there is no coherent
snapshot. Original raw ids were not retained, so cross-run source/target
identity overlap cannot be verified; aliases must not be matched across files.
The earlier two-candidate Task screening is a separate historical measurement.

Identifiers are replaced with stable, run-local `Type/REDACTED-01` pseudonyms
before output, including sources, targets, and the SMART registration path.
Display text, business identifiers, extension URLs, raw errors, and resource
bodies are omitted. Pseudonyms preserve repeated-reference relationships and
are not replayable sandbox ids; they do not guarantee anonymization of graph
structure. The default private output location remains appropriate for review
before publication. This is deterministic diagnostic code, with no LLM.
