from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bundle_assembler import AssemblyIssue, BundleAssembler, BundleAssemblyError
from src.fhir_client import FHIRClient, FHIRClientError
from src.mapping import build_review_packet
from src.models import PacketStatus
from src.parser import BundleValidationError, parse_bundle
from src.utils import now_iso


DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs/realism_sweep.md"
MAX_SWEEP_SIZE = 50
_STATUS_ORDER = (
    PacketStatus.REVIEW_READY.value,
    PacketStatus.INCOMPLETE.value,
    PacketStatus.HUMAN_CONFIRMATION_REQUIRED.value,
)


@dataclass
class RealismSweepResult:
    base_url: str
    requested_limit: int
    discovered_service_requests: int = 0
    reviewed_service_requests: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    missing_element_counts: Counter[str] = field(default_factory=Counter)
    ambiguous_element_counts: Counter[str] = field(default_factory=Counter)
    assembly_failure_counts: Counter[str] = field(default_factory=Counter)
    discovery_issue_counts: Counter[str] = field(default_factory=Counter)
    service_requests_with_assembly_failures: int = 0
    root_assembly_failures: int = 0

    @property
    def resource_assembly_failures(self) -> int:
        return sum(self.assembly_failure_counts.values())


def discover_service_request_ids(
    client: FHIRClient,
    *,
    limit: int,
) -> tuple[list[str], Counter[str]]:
    """Read search pages and retain only bounded, valid ServiceRequest ids."""

    _validate_limit(limit)
    ids: list[str] = []
    seen_ids: set[str] = set()
    seen_next_urls: set[str] = set()
    issues: Counter[str] = Counter()
    next_url: str | None = None

    while len(ids) < limit:
        page = client.get_search_bundle(
            "ServiceRequest",
            count=min(limit - len(ids), MAX_SWEEP_SIZE),
            page_url=next_url,
        )
        entries = page.get("entry", [])
        if not isinstance(entries, list):
            issues["malformed_search_entries"] += 1
            break
        for entry in entries:
            if len(ids) >= limit:
                break
            resource = entry.get("resource") if isinstance(entry, dict) else None
            resource_id = resource.get("id") if isinstance(resource, dict) else None
            if (
                not isinstance(resource, dict)
                or resource.get("resourceType") != "ServiceRequest"
                or not _is_valid_fhir_id(resource_id)
            ):
                issues["invalid_search_entry"] += 1
                continue
            if resource_id in seen_ids:
                issues["duplicate_search_result"] += 1
                continue
            ids.append(resource_id)
            seen_ids.add(resource_id)

        if len(ids) >= limit:
            break
        next_url = _next_link(page)
        if next_url is None:
            break
        if next_url in seen_next_urls:
            issues["pagination_cycle"] += 1
            break
        seen_next_urls.add(next_url)

    return ids, issues


def run_realism_sweep(
    client: FHIRClient,
    *,
    limit: int,
    assembler_factory: Callable[[FHIRClient], Any] = BundleAssembler,
) -> RealismSweepResult:
    """Run deterministic review over discovered ids and keep aggregates only."""

    _validate_limit(limit)
    service_request_ids, discovery_issues = discover_service_request_ids(
        client,
        limit=limit,
    )
    result = RealismSweepResult(
        base_url=client.base_url,
        requested_limit=limit,
        discovered_service_requests=len(service_request_ids),
        discovery_issue_counts=discovery_issues,
    )
    assembler = assembler_factory(client)

    for service_request_id in service_request_ids:
        try:
            assembly = assembler.assemble(service_request_id)
            parsed_bundle = parse_bundle(assembly.bundle)
            parsed_bundle.input_provenance = assembly.input_provenance
            packet = build_review_packet(parsed_bundle)
        except (BundleAssemblyError, BundleValidationError, FHIRClientError, ValueError) as error:
            result.root_assembly_failures += 1
            result.assembly_failure_counts[
                f"root_{type(error).__name__}"
            ] += 1
            continue

        result.reviewed_service_requests += 1
        result.status_counts[packet.status.value] += 1
        result.missing_element_counts.update(packet.missing_elements)
        result.ambiguous_element_counts.update(packet.ambiguous_elements)
        if assembly.issues:
            result.service_requests_with_assembly_failures += 1
            result.assembly_failure_counts.update(
                issue.reason if isinstance(issue, AssemblyIssue) else "invalid_assembly_issue"
                for issue in assembly.issues
            )

    return result


def render_realism_report(
    result: RealismSweepResult,
    *,
    generated_at: str | None = None,
) -> str:
    generated_at = generated_at or now_iso()
    lines = [
        "# FHIR Sandbox Realism Sweep",
        "",
        f"Generated: {generated_at}",
        "",
        (
            "This report contains aggregate review findings only. Raw server resources, "
            "resource IDs, and patient-level values are not retained."
        ),
        "",
        (
            "The public HAPI sandbox is periodically wiped, so its contents and returned "
            "resource IDs are not stable."
        ),
        "",
        "## Scope",
        "",
        f"- Server base URL: `{result.base_url}`",
        f"- Requested maximum ServiceRequests: {result.requested_limit}",
        f"- ServiceRequests discovered: {result.discovered_service_requests}",
        f"- ServiceRequests reviewed: {result.reviewed_service_requests}",
        f"- ServiceRequests failing root assembly: {result.root_assembly_failures}",
        "",
        "## Status distribution",
        "",
        "| Status | Count | Percent of reviewed |",
        "| --- | ---: | ---: |",
    ]
    for status in _STATUS_ORDER:
        count = result.status_counts[status]
        percent = (
            100 * count / result.reviewed_service_requests
            if result.reviewed_service_requests
            else 0
        )
        lines.append(f"| `{status}` | {count} | {percent:.1f}% |")

    lines.extend(_render_counter_section("Most common missing elements", result.missing_element_counts))
    lines.extend(
        _render_counter_section(
            "Most common ambiguous elements",
            result.ambiguous_element_counts,
        )
    )
    lines.extend(
        [
            "",
            "## Assembly failures",
            "",
            (
                "An assembly failure means a referenced resource could not be safely "
                "resolved or a root ServiceRequest could not be reviewed."
            ),
            "",
            (
                "- ServiceRequests with one or more reference/resource assembly failures: "
                f"{result.service_requests_with_assembly_failures}"
            ),
            f"- Total assembly failures: {result.resource_assembly_failures}",
        ]
    )
    lines.extend(_render_counter_table(result.assembly_failure_counts, empty="No assembly failures observed."))
    lines.extend(
        _render_counter_section(
            "Search and pagination observations",
            result.discovery_issue_counts,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "These counts describe how the existing deterministic parser behaved on "
                "the sandbox sample. A high incomplete or confirmation-required rate is "
                "reported as a workflow finding, not treated as a software failure."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_realism_report(
    result: RealismSweepResult,
    *,
    output_path: Path = DEFAULT_REPORT_PATH,
    generated_at: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_realism_report(result, generated_at=generated_at),
        encoding="utf-8",
    )
    return output_path


def _next_link(bundle: dict[str, Any]) -> str | None:
    links = bundle.get("link")
    if not isinstance(links, list):
        return None
    for link in links:
        if not isinstance(link, dict) or link.get("relation") != "next":
            continue
        url = link.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _render_counter_section(title: str, counts: Counter[str]) -> list[str]:
    return ["", f"## {title}", *_render_counter_table(counts, empty="None observed.")]


def _render_counter_table(counts: Counter[str], *, empty: str) -> list[str]:
    if not counts:
        return ["", empty]
    lines = ["", "| Element or reason | Count |", "| --- | ---: |"]
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{name}` | {count} |")
    return lines


def _is_valid_fhir_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9.-]{1,64}", value) is not None
    )


def _validate_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SWEEP_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_SWEEP_SIZE}.")
    return value


def _limit_argument(value: str) -> int:
    try:
        return _validate_limit(int(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review a bounded sample of public-sandbox ServiceRequests and write "
            "an aggregate-only realism report."
        )
    )
    parser.add_argument("--limit", type=_limit_argument, default=10)
    parser.add_argument(
        "--base-url",
        help="FHIR R4 server base URL (defaults to FHIR_BASE_URL or public HAPI).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        client = FHIRClient(base_url=args.base_url) if args.base_url else FHIRClient()
        result = run_realism_sweep(client, limit=args.limit)
        output_path = write_realism_report(result)
    except (FHIRClientError, BundleAssemblyError, BundleValidationError, ValueError) as error:
        print(f"Unable to complete realism sweep: {error}", file=sys.stderr)
        return 1
    print(f"Saved aggregate report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
