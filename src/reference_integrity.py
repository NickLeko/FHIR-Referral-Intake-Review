"""Read-only FHIR R4 Reference inventory, resolution, and aggregate reporting.

Uses FHIRClient for all auth, safe URL resolution, HTTP validation and retries.
This diagnostic is independent of referral parsing and human-reviewed delivery.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import random
import time
from urllib.parse import urlsplit

from src.auth import FHIRAuthError
from src.fhir_client import (
    FHIRClient,
    FHIRClientError,
    FHIRReferenceError,
    FHIRRetryLaterError,
    _FHIR_REFERENCE_RE,
)
from src.utils import save_json_file

SHAPES = json.loads(
    (
        Path(__file__).resolve().parents[1] / "data/fhir_r4_reference_shapes.json"
    ).read_text()
)
RESOURCE_TYPES = frozenset(SHAPES["resources"])
BROKEN = {"gone_410", "not_found_404", "missing_contained"}
NONFAILURES = {
    "resolved_200",
    "resolved_contained",
    "display_only",
    "logical",
    "canonical",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def walk_references(resource):
    """Yield typed Reference nodes, including nested/extension references.

    Paths use only official schema keys, never untrusted extension URLs/keys.
    Contained references are resolved in their containing resource's scope.
    """

    def walk(node, typ, path, scope, owner, depth=0):
        if depth > 64:
            yield path, None, "inventory_limit", scope, owner
            return
        if typ == "ResourceList":
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("resourceType"), str)
                or node.get("resourceType") not in RESOURCE_TYPES
            ):
                yield path, None, "inventory_shape_error", scope, owner
                return
            typ = node["resourceType"]
            owner = typ
            if ".contained[" not in path:
                scope = node
        if typ == "canonical":
            yield path, node, "canonical", scope, owner
            return
        if typ == "Reference":
            yield path, node, "Reference", scope, owner
        if not isinstance(node, dict):
            if typ != "Reference":
                yield path, None, "inventory_shape_error", scope, owner
            return
        for key, (child_type, array) in SHAPES["shapes"].get(typ, {}).items():
            if key not in node:
                continue
            value = node[key]
            child_path = f"{path}.{key}"
            if array:
                if not isinstance(value, list):
                    yield child_path, None, "inventory_shape_error", scope, owner
                    continue
                for index, child in enumerate(value):
                    yield from walk(
                        child,
                        child_type,
                        f"{child_path}[{index}]",
                        scope,
                        owner,
                        depth + 1,
                    )
            else:
                yield from walk(value, child_type, child_path, scope, owner, depth + 1)

    yield from walk(
        resource,
        resource["resourceType"],
        resource["resourceType"],
        resource,
        resource["resourceType"],
    )


def public_server(base_url):
    parts = urlsplit(base_url)
    if "/sim/" in parts.path:
        path = re.sub(r"(/sim/)[^/]+", r"\1REDACTED-REGISTRATION", parts.path)
    elif parts.path in ("", "/baseR4", "/fhir", "/v/r4/fhir"):
        path = parts.path
    else:
        path = "/REDACTED-BASE-PATH"
    return (
        f"{parts.scheme}://{parts.hostname}"
        + (f":{parts.port}" if parts.port else "")
        + path
    )


class IntegrityRun:
    def __init__(
        self, client, *, min_interval=0.25, sleep=time.sleep, monotonic=time.monotonic
    ):
        if not 0 <= min_interval <= 60:
            raise ValueError("min_interval must be between 0 and 60 seconds")
        self.client = client
        self.interval, self.sleep, self.clock = min_interval, sleep, monotonic
        self.last_call = None
        self.aliases, self.alias_counts = {}, Counter()
        self.cache = {}
        self.lookup_count = 0
        self.cache_hits = 0
        self.halt = None

    def alias(self, typ, key):
        token = (typ, key)
        if token not in self.aliases:
            self.alias_counts[typ] += 1
            self.aliases[token] = f"{typ}/REDACTED-{self.alias_counts[typ]:02d}"
        return self.aliases[token]

    def call(self, fn, *args, **kwargs):
        if self.last_call is not None:
            delay = self.interval - (self.clock() - self.last_call)
            if delay > 0:
                self.sleep(delay)
        try:
            return fn(*args, **kwargs)
        finally:
            self.last_call = self.clock()

    @staticmethod
    def error(error):
        return {
            "error_type": type(error).__name__,
            "http_status": getattr(error, "status_code", None),
        }

    def sample(self, typ, size, *, method, skip, seed, max_scan):
        sources, seen, pages_seen = [], set(), set()
        rng = random.Random(seed)
        page_url = None
        info = {
            "method": method,
            "skip_requested": skip,
            "random_seed": seed if method == "reservoir" else None,
            "scan_limit": max_scan,
            "scanned_unique_sources": 0,
            "eligible_sources": 0,
            "population_exhausted": False,
            "pages": 0,
            "duplicates_skipped": 0,
            "complete": False,
            "stop_reason": None,
        }
        for _ in range(max(10, max_scan // 10)):
            try:
                page = self.call(
                    self.client.get_search_bundle,
                    typ,
                    count=50
                    if method == "reservoir" or skip
                    else min(50, size - len(sources)),
                    page_url=page_url,
                )
            except FHIRClientError as error:
                info.update(stop_reason="search_error", error=self.error(error))
                if isinstance(error, (FHIRRetryLaterError, FHIRAuthError)) or getattr(
                    error, "status_code", None
                ) in (401, 403):
                    self.halt = self.error(error)
                break
            info["pages"] += 1
            entries = page.get("entry", [])
            page_truncated = False
            for entry_index, entry in enumerate(entries):
                resource = entry["resource"]
                if resource["id"] in seen:
                    info["duplicates_skipped"] += 1
                    continue
                seen.add(resource["id"])
                position = len(seen)
                info["scanned_unique_sources"] = position
                if position > skip:
                    info["eligible_sources"] += 1
                    if len(sources) < size:
                        sources.append((position, resource))
                    elif method == "reservoir":
                        slot = rng.randrange(info["eligible_sources"])
                        if slot < size:
                            sources[slot] = (position, resource)
                if (
                    method == "sequential" and len(sources) == size
                ) or position == max_scan:
                    page_truncated = entry_index + 1 < len(entries)
                    break
            if method == "sequential" and len(sources) == size:
                info.update(complete=True, stop_reason="requested_sample_reached")
                break
            next_links = [
                link["url"]
                for link in page.get("link", [])
                if link["relation"] == "next"
            ]
            if len(seen) >= max_scan and (page_truncated or next_links):
                info["stop_reason"] = "scan_limit_reached"
                break
            if not next_links:
                info["stop_reason"] = "server_exhausted"
                info["population_exhausted"] = True
                info["complete"] = len(sources) == size
                break
            if len(next_links) != 1 or next_links[0] in pages_seen:
                info["stop_reason"] = "ambiguous_or_cyclic_pagination"
                break
            page_url = next_links[0]
            pages_seen.add(page_url)
        else:
            info["stop_reason"] = "page_budget_exhausted"
        sources.sort(key=lambda item: item[0])
        info["selected_stream_positions"] = [position for position, _ in sources]
        return [resource for _, resource in sources], info

    def resolve(self, value, scope):
        result = {
            "target_resource_type": "Unknown",
            "target": None,
            "http_status": None,
            "cache_hit": False,
            "lookup_attempted": False,
        }

        def outcome(name, **kwargs):
            return {**result, "outcome": name, **kwargs}

        if not isinstance(value, dict):
            return outcome("unresolvable_invalid")
        declared = value.get("type")
        if not isinstance(declared, str):
            declared = None
        if isinstance(declared, str):
            declared = declared.removeprefix("http://hl7.org/fhir/StructureDefinition/")
            if declared in RESOURCE_TYPES:
                result["target_resource_type"] = declared
        literal = value.get("reference")
        if not literal:
            if isinstance(value.get("identifier"), dict) and value["identifier"]:
                return outcome("logical")
            if isinstance(value.get("display"), str) and value["display"].strip():
                return outcome("display_only")
            return outcome("unresolvable_invalid")
        if not isinstance(literal, str):
            return outcome("unresolvable_invalid")
        if literal.startswith("#"):
            contained = scope.get("contained", [])
            matches = (
                [
                    r
                    for r in contained
                    if isinstance(r, dict) and r.get("id") == literal[1:]
                ]
                if isinstance(contained, list)
                else []
            )
            if literal == "#":
                matches = [scope]
            result["target"] = self.alias("Contained", (id(scope), literal))
            if (
                len(matches) == 1
                and isinstance(matches[0].get("resourceType"), str)
                and matches[0]["resourceType"] in RESOURCE_TYPES
            ):
                result["target_resource_type"] = matches[0]["resourceType"]
                if (
                    declared in RESOURCE_TYPES
                    and declared != result["target_resource_type"]
                ):
                    return outcome("unresolvable_type_mismatch")
                return outcome("resolved_contained")
            return outcome("missing_contained")
        if literal.startswith("urn:"):
            result["target"] = self.alias(
                result["target_resource_type"], ("urn", literal)
            )
            return outcome("unresolvable_no_rest_id")
        try:
            relative = self.client._local_relative_reference(literal)
        except FHIRReferenceError:
            # Infer a type without retaining the untrusted URL, but never follow it.
            match = re.search(r"/([A-Z][A-Za-z0-9]+)/[^/]+$", literal)
            if match and match[1] in RESOURCE_TYPES:
                result["target_resource_type"] = match[1]
            result["target"] = self.alias(
                result["target_resource_type"], ("blocked", literal)
            )
            return outcome("unresolvable_external_or_unsafe")
        match = _FHIR_REFERENCE_RE.fullmatch(relative)
        if not match or match["resource_type"] not in RESOURCE_TYPES:
            result["target"] = self.alias(
                result["target_resource_type"], ("invalid", literal)
            )
            return outcome("unresolvable_no_rest_id")
        typ = match["resource_type"]
        result["target_resource_type"] = typ
        result["target"] = self.alias(typ, relative)
        if declared in RESOURCE_TYPES and declared != typ:
            return outcome("unresolvable_type_mismatch")
        if relative in self.cache:
            self.cache_hits += 1
            return {**result, **self.cache[relative], "cache_hit": True}
        if self.halt:
            return outcome("not_attempted", error_type=self.halt["error_type"])
        self.lookup_count += 1
        try:
            fetched = self.call(self.client.get_reference, relative, typ)
            status = fetched.http_status
            answer = {
                "outcome": "resolved_200" if status == 200 else "other_error",
                "http_status": status,
                "lookup_attempted": True,
            }
        except FHIRClientError as error:
            status = getattr(error, "status_code", None)
            answer = {
                "outcome": {404: "not_found_404", 410: "gone_410"}.get(
                    status, "other_error"
                ),
                **self.error(error),
                "lookup_attempted": True,
            }
            if isinstance(error, (FHIRRetryLaterError, FHIRAuthError)) or status in (
                401,
                403,
            ):
                self.halt = self.error(error)
        self.cache[relative] = answer
        return {**result, **answer}

    def run(
        self,
        resource_type,
        sample_size,
        *,
        progress=None,
        sampling_method="sequential",
        skip=0,
        seed=0,
        max_scan=10000,
    ):
        if resource_type not in RESOURCE_TYPES:
            raise ValueError("resource_type must be a FHIR R4 resource type")
        if (
            isinstance(sample_size, bool)
            or not isinstance(sample_size, int)
            or not 1 <= sample_size <= 10000
        ):
            raise ValueError("sample_size must be between 1 and 10000")
        if sampling_method not in {"sequential", "reservoir"}:
            raise ValueError("unknown sampling method")
        if (
            not isinstance(skip, int)
            or isinstance(skip, bool)
            or skip < 0
            or not isinstance(max_scan, int)
            or isinstance(max_scan, bool)
            or not sample_size + skip <= max_scan <= 100000
            or not isinstance(seed, int)
            or isinstance(seed, bool)
        ):
            raise ValueError("invalid sampling bounds or seed")
        started = utc_now()
        # A reusable runner must not carry stale targets or aliases between samples.
        self.cache.clear()
        self.aliases.clear()
        self.alias_counts.clear()
        self.lookup_count = self.cache_hits = 0
        self.halt = None
        resources, sampling = self.sample(
            resource_type,
            sample_size,
            method=sampling_method,
            skip=skip,
            seed=seed,
            max_scan=max_scan,
        )
        rows, sources, inventory_issues, canonical_count = [], [], [], 0
        for index, resource in enumerate(resources, 1):
            source = self.alias(resource_type, f"{resource_type}/{resource['id']}")
            source_rows = []
            for path, value, kind, scope, owner in walk_references(resource):
                if kind == "canonical":
                    canonical_count += 1
                    continue
                if kind != "Reference":
                    inventory_issues.append(
                        {"source": source, "field_path": path, "reason": kind}
                    )
                    continue
                row = {
                    "source": source,
                    "source_resource_type": owner,
                    "field_path": path,
                    "field_group": re.sub(r"\[\d+\]", "[]", path),
                    **self.resolve(value, scope),
                }
                rows.append(row)
                source_rows.append(row)
            sources.append(
                {
                    "source": source,
                    "reference_count": len(source_rows),
                    "has_broken_reference": any(
                        r["outcome"] in BROKEN for r in source_rows
                    ),
                    "has_resolution_problem": any(
                        r["outcome"] not in NONFAILURES for r in source_rows
                    )
                    or any(issue["source"] == source for issue in inventory_issues),
                }
            )
            if progress:
                progress(index, len(resources))
        return {
            "format_version": 1,
            "server": public_server(self.client.base_url),
            "source_resource_type": resource_type,
            "requested_sample_size": sample_size,
            "sampled_resources": len(resources),
            "started_at": started,
            "finished_at": utc_now(),
            "sampling": sampling,
            "halt": self.halt,
            "inventory_issues": inventory_issues,
            "canonical_fields_excluded": canonical_count,
            "unique_target_lookups": self.lookup_count,
            "cache_hits": self.cache_hits,
            "sources": sources,
            "references": rows,
            "summary": summarize(rows, sources),
            "clustering": reference_clusters(rows),
            "by_target_type": group_summary(rows, "target_resource_type"),
            "by_source_field": group_summary(rows, "field_group"),
            "reference_count_distribution": dict(
                sorted(Counter(s["reference_count"] for s in sources).items())
            ),
            "notes": [
                "One public sandbox at one moment. Sequential sampling measures a contiguous returned cohort; reservoir sampling covers only its documented eligible stream, not production prevalence.",
                "All ids are run-local pseudonyms. No raw payloads, display text, logical identifiers, or credential values are retained.",
                "Distinct-target resolution describes queried target state. Occurrence resolution describes downstream exposure to those same targets, including cached outcomes; it is not an independent server-state estimate. Transport retries may add HTTP requests.",
                "Known broken means 404, 410 or missing contained target. Errors and blocked/unattempted refs are reported separately; known-broken source fraction is a lower bound when these exist.",
                "Logical and display-only references are not broken and are excluded from HTTP denominators. Contained targets are checked locally, never reported as HTTP 200.",
                "All standard R4 Reference fields in sampled JSON are walked, including extensions and contained resources. Canonical fields are counted separately, not dereferenced. Resolved targets are not recursively crawled.",
                "Out-of-server or unsafe URLs are not followed. Auth scopes are unchanged. Rate-limit deferral or auth failure halts new lookups; no anonymous fallback.",
                "A successful GET proves readability and identity at lookup time, not semantic consistency or a coherent snapshot. Cache entries, including failures, last for this run only.",
            ],
        }


def rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": round(100 * numerator / denominator, 4) if denominator else None,
    }


def summarize(rows, sources=None):
    counts = Counter(r["outcome"] for r in rows)
    attempted = sum(r["lookup_attempted"] for r in rows)
    unique = {r["target"]: r for r in rows if r["lookup_attempted"]}
    unique_counts = Counter(r["outcome"] for r in unique.values())
    result = {
        "unique_http_resolution_rate": rate(unique_counts["resolved_200"], len(unique)),
        "unique_http_outcomes": dict(sorted(unique_counts.items())),
        "reference_occurrences": len(rows),
        "unique_http_broken_targets": unique_counts["gone_410"]
        + unique_counts["not_found_404"],
        "outcomes": dict(sorted(counts.items())),
        "http_resolution_rate": rate(counts["resolved_200"], attempted),
        "known_broken_references": sum(counts[k] for k in BROKEN),
        "http_status_counts": dict(
            sorted(
                Counter(
                    str(r["http_status"]) for r in rows if r["http_status"] is not None
                ).items()
            )
        ),
    }
    if sources is not None:
        result["sources_with_broken_reference"] = rate(
            sum(s["has_broken_reference"] for s in sources), len(sources)
        )
        result["sources_with_resolution_problem"] = rate(
            sum(s["has_resolution_problem"] for s in sources), len(sources)
        )
    return result


def group_summary(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: summarize(values) for name, values in sorted(groups.items())}


def reference_clusters(rows):
    targets, signatures = defaultdict(set), defaultdict(set)
    occurrences = Counter()
    for row in rows:
        if row["outcome"] in BROKEN and row["target"]:
            targets[row["target"]].add(row["source"])
            signatures[row["source"]].add(row["target"])
            occurrences[row["target"]] += 1
    groups = Counter(tuple(sorted(values)) for values in signatures.values())
    return {
        "broken_target_fanout": [
            {
                "target": target,
                "source_count": len(sources),
                "reference_occurrences": occurrences[target],
            }
            for target, sources in sorted(
                targets.items(), key=lambda item: (-len(item[1]), item[0])
            )
        ],
        "shared_broken_target_sets": [
            {"targets": list(target_set), "source_count": count}
            for target_set, count in sorted(
                groups.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def render_report(report):
    def fmt(value):
        pct = "undefined" if value["percent"] is None else f"{value['percent']:.2f}%"
        return f"{value['numerator']}/{value['denominator']} ({pct})"

    s = report["summary"]
    lines = [
        "# Reference-integrity report",
        "",
        f"Server: `{report['server']}`",
        "",
        f"Started: {report['started_at']} | Finished: {report['finished_at']}",
        "",
        f"Requested: {report['requested_sample_size']} {report['source_resource_type']} resources; sampled: **{report['sampled_resources']}**.",
        f"Sampling stop: `{report['sampling']['stop_reason']}`; pages: {report['sampling']['pages']}; duplicate sources skipped: {report['sampling']['duplicates_skipped']}.",
        "",
        f"Distinct-target resolution (queried server state): **{fmt(s['unique_http_resolution_rate'])}** distinct queried targets.",
        "",
        f"Occurrence resolution (downstream exposure): **{fmt(s['http_resolution_rate'])}**, based on those same **{s['unique_http_resolution_rate']['denominator']} distinct targets**, with **{report['cache_hits']} cache hits**.",
        "Repeated references inherit a target's cached outcome. The occurrence rate weights targets by how often this source sample references them; it is not a second independent measurement of server state.",
        "",
        f"Sources with at least one known broken reference: **{fmt(s['sources_with_broken_reference'])}**.",
        f"Sources with any resolution problem (including unknown outcomes): **{fmt(s['sources_with_resolution_problem'])}**.",
        "",
        f"Reference occurrences: {s['reference_occurrences']}; unique target lookups: {report['unique_target_lookups']}; cache hits: {report['cache_hits']}.",
        f"Canonical fields excluded: {report['canonical_fields_excluded']}; inventory shape issues: {len(report['inventory_issues'])}.",
        "",
        "## Outcome classes",
        "",
        "| Outcome | Reference occurrences |",
        "| --- | ---: |",
    ]
    lines += [f"| {k} | {v} |" for k, v in s["outcomes"].items()]
    for title, key in [
        ("By target resource type", "by_target_type"),
        ("By source field path", "by_source_field"),
    ]:
        lines += [
            "",
            f"## {title}",
            "",
            "| Group | Distinct resolved / queried targets | Distinct broken HTTP targets | References | Occurrence resolved / attempted (same distinct targets) | Broken occurrences | Other errors |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: |",
        ]
        for name, g in sorted(
            report[key].items(),
            key=lambda item: (-item[1]["unique_http_broken_targets"], item[0]),
        ):
            lines.append(
                f"| `{name}` | {fmt(g['unique_http_resolution_rate'])} | {g['unique_http_broken_targets']} | {g['reference_occurrences']} | {fmt(g['http_resolution_rate'])} | {g['known_broken_references']} | {g['outcomes'].get('other_error', 0)} |"
            )
    sampling_design = {
        k: v for k, v in report["sampling"].items() if k != "selected_stream_positions"
    }
    positions = report["sampling"].get("selected_stream_positions", [])
    if positions:
        sampling_design["selected_position_min_max"] = [min(positions), max(positions)]
        sampling_design["adjacent_selected_pairs"] = sum(
            b == a + 1 for a, b in zip(positions, positions[1:])
        )
    lines += [
        "",
        "## Sampling design",
        "",
        "```json",
        json.dumps(sampling_design, indent=2),
        "```",
        "",
        "## Broken-target clustering",
        "",
        "Largest groups of sources sharing exactly the same set of broken targets (up to ten; all groups in JSON). Pseudonyms are local to this report, not comparable ids across runs.",
        "",
        "| Sources | Shared broken targets |",
        "| ---: | --- |",
    ]
    for group in report["clustering"]["shared_broken_target_sets"][:10]:
        lines.append(f"| {group['source_count']} | {', '.join(group['targets'])} |")
    lines += [
        "",
        "## References per sampled source",
        "",
        "| Reference count | Sources |",
        "| ---: | ---: |",
    ]
    lines += [
        f"| {n} | {count} |"
        for n, count in report["reference_count_distribution"].items()
    ]
    lines += ["", "## Measurement boundaries", ""] + [
        "- " + note for note in report["notes"]
    ]
    if report["halt"] or report["sampling"].get("error"):
        lines += [
            "",
            "Run ended with a transport/auth sampling or resolution limitation: `"
            + json.dumps(report["halt"] or report["sampling"]["error"])
            + "`.",
        ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resource-type", required=True, choices=sorted(RESOURCE_TYPES)
    )
    parser.add_argument("--sample-size", required=True, type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/integration/reference-integrity"),
    )
    parser.add_argument("--base-url")
    parser.add_argument("--min-interval", type=float, default=0.25)
    parser.add_argument(
        "--sampling", choices=["sequential", "reservoir"], default="sequential"
    )
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-scan", type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        run = IntegrityRun(
            FHIRClient(base_url=args.base_url), min_interval=args.min_interval
        )
        report = run.run(
            args.resource_type,
            args.sample_size,
            sampling_method=args.sampling,
            skip=args.skip,
            seed=args.seed,
            max_scan=args.max_scan,
            progress=lambda n, total: print(
                f"Inventoried {n}/{total} sources", flush=True
            )
            if n % 10 == 0 or n == total
            else None,
        )
        save_json_file(args.output_dir / "report.json", report)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.md").write_text(render_report(report))
    except (FHIRClientError, ValueError, OSError) as error:
        print(
            f"Reference-integrity run failed: {type(error).__name__}. No anonymous fallback."
        )
        return 1
    print(
        json.dumps(
            {
                "sampled_resources": report["sampled_resources"],
                "summary": report["summary"],
            }
        )
    )
    return (
        2
        if report["halt"]
        or report["inventory_issues"]
        or report["sampling"]["stop_reason"]
        not in ("requested_sample_reached", "server_exhausted")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
