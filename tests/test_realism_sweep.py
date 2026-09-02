from __future__ import annotations

from pathlib import Path

import pytest

from scripts.realism_sweep import (
    RealismSweepResult,
    discover_service_request_ids,
    render_realism_report,
    run_realism_sweep,
    write_realism_report,
)
from src.bundle_assembler import AssemblyIssue, BundleAssemblyResult
from src.models import InputProvenance
from src.utils import load_json_file


class FakeSearchClient:
    base_url = "https://example.test/fhir"

    def __init__(self, pages: list[dict]) -> None:
        self.pages = list(pages)
        self.calls: list[dict] = []

    def get_search_bundle(self, resource_type: str, **kwargs) -> dict:
        self.calls.append({"resource_type": resource_type, **kwargs})
        return self.pages.pop(0)


def _search_page(ids: list[str], next_url: str | None = None) -> dict:
    page = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {"resource": {"resourceType": "ServiceRequest", "id": resource_id}}
            for resource_id in ids
        ],
    }
    if next_url:
        page["link"] = [{"relation": "next", "url": next_url}]
    return page


def test_discovery_paginates_and_stops_at_the_requested_limit() -> None:
    client = FakeSearchClient(
        [
            _search_page(["sr-1", "sr-2"], "https://example.test/fhir?page=2"),
            _search_page(["sr-3", "sr-4"]),
        ]
    )

    ids, issues = discover_service_request_ids(client, limit=3)

    assert ids == ["sr-1", "sr-2", "sr-3"]
    assert issues == {}
    assert len(client.calls) == 2
    assert client.calls[1]["page_url"] == "https://example.test/fhir?page=2"


class FixtureAssembler:
    def __init__(self, _client) -> None:
        pass

    def assemble(self, service_request_id: str) -> BundleAssemblyResult:
        filenames = {
            "sr-ready": "bundle_001_review_ready.json",
            "sr-incomplete": "bundle_002_incomplete.json",
            "sr-confirm": "bundle_003_human_confirmation.json",
        }
        issues = []
        if service_request_id == "sr-incomplete":
            issues = [
                AssemblyIssue(
                    field="reasonReference[0]",
                    reference="Condition/missing",
                    reason="fetch_failed",
                )
            ]
        return BundleAssemblyResult(
            bundle=load_json_file(Path("data/sample_bundles") / filenames[service_request_id]),
            input_provenance=InputProvenance(source_type="live"),
            issues=issues,
        )


def test_sweep_aggregates_status_issues_and_failures_without_ids() -> None:
    client = FakeSearchClient(
        [_search_page(["sr-ready", "sr-incomplete", "sr-confirm"])]
    )

    result = run_realism_sweep(
        client,
        limit=3,
        assembler_factory=FixtureAssembler,
    )
    report = render_realism_report(
        result,
        generated_at="2026-09-02T12:00:00+00:00",
    )

    assert result.reviewed_service_requests == 3
    assert result.status_counts == {
        "REVIEW_READY": 1,
        "INCOMPLETE": 1,
        "HUMAN_CONFIRMATION_REQUIRED": 1,
    }
    assert result.missing_element_counts["ordering_provider"] == 1
    assert result.ambiguous_element_counts["requested_service"] == 1
    assert result.assembly_failure_counts["fetch_failed"] == 1
    assert "sr-ready" not in report
    assert "| `INCOMPLETE` | 1 | 33.3% |" in report


def test_report_writer_creates_one_aggregate_markdown_file(tmp_path) -> None:
    result = RealismSweepResult(
        base_url="https://example.test/fhir",
        requested_limit=5,
    )
    output_path = write_realism_report(
        result,
        output_path=tmp_path / "realism_sweep.md",
        generated_at="2026-09-02T12:00:00+00:00",
    )

    assert output_path.read_text(encoding="utf-8").startswith(
        "# FHIR Sandbox Realism Sweep"
    )
    assert list(tmp_path.iterdir()) == [output_path]


def test_sweep_limit_is_capped_at_fifty() -> None:
    with pytest.raises(ValueError, match="between 1 and 50"):
        discover_service_request_ids(FakeSearchClient([]), limit=51)
