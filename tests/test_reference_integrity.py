from collections import deque
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from src.reference_integrity import (
    IntegrityRun,
    render_report,
    walk_references,
    public_server,
    main,
)
from test_integration import MockFHIRServer, make_client


def source(sid="s-one", **fields):
    return {"resourceType": "ServiceRequest", "id": sid, **fields}


def page(resources, next_url=None):
    body = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": r} for r in resources],
    }
    if next_url:
        body["link"] = [{"relation": "next", "url": next_url}]
    return body


class SearchServer(MockFHIRServer):
    def __init__(self, pages):
        super().__init__()
        self.pages = deque(pages)

    def send(self, request, **kwargs):
        if urlsplit(request.url).path in ("/fhir/ServiceRequest", "/fhir/Patient"):
            self.calls.append(request)
            item = self.pages.popleft()
            if isinstance(item, tuple):
                return self.response(request, *item)
            return self.response(request, body=item)
        return super().send(request, **kwargs)


def run(server, size=100, **kwargs):
    return IntegrityRun(make_client(server), min_interval=0, **kwargs).run(
        "ServiceRequest", size
    )


@pytest.mark.parametrize(
    "status,outcome",
    [
        (200, "resolved_200"),
        (404, "not_found_404"),
        (410, "gone_410"),
        (500, "other_error"),
        (403, "other_error"),
    ],
)
def test_http_outcome_and_real_status(status, outcome):
    server = SearchServer([page([source(subject={"reference": "Patient/private-id"})])])
    server.resources["Patient/private-id"] = {
        "resourceType": "Patient",
        "id": "private-id",
    }
    if status != 200:
        server.faults[("GET", "/fhir/Patient/private-id")].extend([status] * 3)
    result = run(server)
    row = result["references"][0]
    assert row["outcome"] == outcome and row["http_status"] == status
    assert result["sampled_resources"] == 1
    assert result["summary"]["http_resolution_rate"]["denominator"] == 1
    assert result["summary"]["sources_with_broken_reference"]["numerator"] == int(
        status in (404, 410)
    )
    assert "private-id" not in json.dumps(result)
    assert "private-id" not in render_report(result)
    assert len([r for r in server.calls if r.url.endswith("/private-id")]) == (
        3 if status == 500 else 1
    )


def test_reference_walker_logical_display_extension_nested_and_coding():
    resource = source(
        subject={"display": "private name"},
        requester={
            "identifier": {"value": "private-logical-id"},
            "type": "Practitioner",
        },
        code={"coding": [{"display": "not a reference"}]},
        extension=[
            {
                "url": "private-extension-url",
                "valueReference": {"reference": "Patient/p"},
            }
        ],
        instantiatesCanonical=["http://private.example/plan"],
    )
    server = SearchServer([page([resource])])
    server.resources["Patient/p"] = {"resourceType": "Patient", "id": "p"}
    r = run(server)
    assert r["summary"]["outcomes"] == {
        "display_only": 1,
        "logical": 1,
        "resolved_200": 1,
    }
    assert r["canonical_fields_excluded"] == 1
    assert r["sources"][0]["reference_count"] == 3
    assert r["summary"]["http_resolution_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "percent": 100.0,
    }
    assert r["by_target_type"]["Practitioner"]["outcomes"] == {"logical": 1}
    assert not r["sources"][0]["has_broken_reference"]
    assert all(
        v not in json.dumps(r)
        for v in [
            "private name",
            "private-logical-id",
            "private-extension-url",
            "private.example",
        ]
    )
    patient = {
        "resourceType": "Patient",
        "id": "p",
        "contact": [{"organization": {"display": "private org"}}],
    }
    assert [x[0] for x in walk_references(patient)] == [
        "Patient.contact[0].organization"
    ]


def test_cache_canonicalizes_relative_and_absolute_and_counts_occurrences():
    server = SearchServer(
        [
            page(
                [
                    source("s1", subject={"reference": "Patient/shared"}),
                    source(
                        "s2",
                        subject={"reference": "https://fhir.test/fhir/Patient/shared"},
                    ),
                ]
            )
        ]
    )
    server.faults[("GET", "/fhir/Patient/shared")].append(410)
    r = run(server)
    assert r["cache_hits"] == 1 and r["unique_target_lookups"] == 1
    assert r["summary"]["unique_http_resolution_rate"]["denominator"] == 1
    assert r["summary"]["http_resolution_rate"]["denominator"] == 2
    assert r["summary"]["sources_with_broken_reference"]["percent"] == 100.0
    assert len([q for q in server.calls if q.url.endswith("/Patient/shared")]) == 1
    assert (
        r["references"][0]["target"]
        == r["references"][1]["target"]
        == "Patient/REDACTED-01"
    )


def test_pagination_deduplicates_and_honors_sample_limit():
    server = SearchServer(
        [
            page(
                [source("a"), source("b")],
                "https://fhir.test/fhir/ServiceRequest?page=2",
            ),
            page([source("b"), source("c"), source("d")]),
        ]
    )
    r = run(server, size=3)
    assert r["sampled_resources"] == 3 and r["sampling"]["complete"]
    assert r["sampling"]["duplicates_skipped"] == 1 and r["sampling"]["pages"] == 2
    assert r["reference_count_distribution"] == {0: 3}
    assert r["summary"]["http_resolution_rate"]["percent"] is None
    assert r["summary"]["sources_with_broken_reference"] == {
        "numerator": 0,
        "denominator": 3,
        "percent": 0.0,
    }


def test_empty_and_cyclic_pages_are_bounded():
    link = "https://fhir.test/fhir/ServiceRequest?page=2"
    r = run(SearchServer([page([], link), page([], link)]))
    assert r["sampling"]["stop_reason"] == "ambiguous_or_cyclic_pagination"
    assert r["sampled_resources"] == 0


def test_contained_scope_is_per_source_and_no_fabricated_http_200():
    ref = {"reference": "#same"}
    first = source(
        "a", subject=ref, contained=[{"resourceType": "Patient", "id": "same"}]
    )
    second = source("b", subject=ref)
    r = run(SearchServer([page([first, second])]))
    assert r["summary"]["outcomes"] == {"missing_contained": 1, "resolved_contained": 1}
    assert r["unique_target_lookups"] == 0
    assert r["summary"]["sources_with_broken_reference"]["percent"] == 50.0
    assert all(x["http_status"] is None for x in r["references"])
    assert r["references"][0]["target"] != r["references"][1]["target"]


def test_external_unsafe_and_urn_references_never_receive_credentials():
    server = SearchServer(
        [
            page(
                [
                    source(
                        subject={"reference": "https://elsewhere.test/Patient/private"},
                        requester={"reference": "urn:uuid:private"},
                        encounter={"reference": "Encounter/../secret"},
                    )
                ]
            )
        ]
    )
    r = run(server)
    assert len(server.calls) == 1 and r["unique_target_lookups"] == 0
    assert r["summary"]["outcomes"] == {
        "unresolvable_external_or_unsafe": 1,
        "unresolvable_no_rest_id": 2,
    }
    assert "private" not in json.dumps(r) and "elsewhere.test" not in json.dumps(r)


def test_rate_limit_backoff_then_success_uses_existing_transport():
    server = SearchServer([page([source(subject={"reference": "Patient/p"})])])
    server.resources["Patient/p"] = {"resourceType": "Patient", "id": "p"}
    server.faults[("GET", "/fhir/Patient/p")].append((429, {}, {"Retry-After": "1"}))
    delays = []
    r = IntegrityRun(make_client(server, sleep=delays.append), min_interval=0).run(
        "ServiceRequest", 1
    )
    assert delays == [1.0] and r["summary"]["outcomes"] == {"resolved_200": 1}


def test_long_rate_limit_defers_remaining_refs_without_hammering():
    server = SearchServer(
        [
            page(
                [
                    source(
                        subject={"reference": "Patient/p"},
                        requester={"reference": "Practitioner/q"},
                    )
                ]
            )
        ]
    )
    server.faults[("GET", "/fhir/Patient/p")].append((429, {}, {"Retry-After": "30"}))
    r = run(server)
    assert r["summary"]["outcomes"] == {"not_attempted": 1, "other_error": 1}
    assert r["halt"]["http_status"] == 429 and r["unique_target_lookups"] == 1
    assert r["summary"]["http_resolution_rate"]["denominator"] == 1
    assert not any(q.url.endswith("/Practitioner/q") for q in server.calls)


def test_shape_errors_and_malformed_200_do_not_masquerade_as_resolved():
    server = SearchServer(
        [
            page(
                [
                    source(
                        subject={"reference": "Patient/p"},
                        supportingInfo="invalid-list",
                    )
                ]
            )
        ]
    )
    server.faults[("GET", "/fhir/Patient/p")].append((200, {"wrong": "shape"}, {}))
    r = run(server)
    assert r["summary"]["outcomes"] == {"other_error": 1}
    assert r["references"][0]["http_status"] == 200
    assert r["inventory_issues"][0]["reason"] == "inventory_shape_error"
    bad = run(SearchServer([{"resourceType": "Patient", "id": "wrong"}]))
    assert (
        bad["sampled_resources"] == 0
        and bad["sampling"]["stop_reason"] == "search_error"
    )


def test_partial_sampling_failure_retains_real_denominator():
    server = SearchServer(
        [page([source("a")], "https://fhir.test/fhir/ServiceRequest?page=2")]
        + [(500, {})] * 3
    )
    r = run(server)
    assert r["sampled_resources"] == 1 and r["sampling"]["error"]["http_status"] == 500
    assert r["summary"]["sources_with_broken_reference"]["denominator"] == 1
    denied = SearchServer(
        [
            page(
                [source(subject={"reference": "Patient/p"})],
                "https://fhir.test/fhir/ServiceRequest?page=2",
            ),
            (403, {}),
        ]
    )
    halted = run(denied)
    assert halted["halt"]["http_status"] == 403
    assert halted["summary"]["outcomes"] == {"not_attempted": 1}
    assert len(denied.calls) == 2


def test_version_specific_refs_have_separate_cache_entries():
    server = SearchServer(
        [
            page(
                [
                    source(
                        subject={"reference": "Patient/p/_history/1"},
                        supportingInfo=[{"reference": "Patient/p/_history/2"}],
                    )
                ]
            )
        ]
    )
    for version in ["1", "2"]:
        server.resources[f"Patient/p/_history/{version}"] = {
            "resourceType": "Patient",
            "id": "p",
        }
    r = run(server)
    assert r["unique_target_lookups"] == 2 and r["summary"]["outcomes"] == {
        "resolved_200": 2
    }


def test_pacing_and_server_pseudonymization():
    server = SearchServer([page([source(subject={"reference": "Patient/p"})])])
    sleeps = []
    run(server, sleep=sleeps.append, monotonic=lambda: 0)  # Zero interval in helper
    paced = IntegrityRun(
        make_client(SearchServer([page([source(subject={"reference": "Patient/p"})])])),
        min_interval=0.25,
        sleep=sleeps.append,
        monotonic=lambda: 0,
    )
    paced.run("ServiceRequest", 1)
    assert sleeps == [0.25]
    assert public_server(
        "https://launch.smarthealthit.org/v/r4/sim/private/fhir"
    ).endswith("/sim/REDACTED-REGISTRATION/fhir")
    assert "private" not in public_server("https://example.test/private/path")


def test_cli_writes_only_pseudonymized_reports(monkeypatch, tmp_path):
    server = SearchServer([page([source(subject={"reference": "Patient/private"})])])
    monkeypatch.setattr(
        "src.reference_integrity.FHIRClient", lambda **kwargs: make_client(server)
    )
    assert (
        main(
            [
                "--resource-type",
                "ServiceRequest",
                "--sample-size",
                "100",
                "--min-interval",
                "0",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert {p.name for p in tmp_path.iterdir()} == {"report.json", "report.md"}
    for p in tmp_path.iterdir():
        assert "private" not in p.read_text()
    assert json.loads((tmp_path / "report.json").read_text())["sampled_resources"] == 1


def test_r4_index_is_pinned_and_reference_metadata_is_not_parser_expansion():
    from src.reference_integrity import SHAPES
    from src.parser import SUPPORTED_RESOURCE_TYPES

    assert SHAPES["fhir_version"] == "4.0.1" and len(SHAPES["resources"]) == 146
    assert SHAPES["shapes"]["ServiceRequest"]["subject"] == ["Reference", False]
    assert len(SUPPORTED_RESOURCE_TYPES) == 7 and "Task" not in SUPPORTED_RESOURCE_TYPES
    assert Path("data/fhir_r4_reference_shapes.json").is_file()


def test_invalid_reference_and_declared_type_mismatch_are_separate_from_deleted():
    server = SearchServer(
        [
            page(
                [
                    source(
                        subject={},
                        requester={"reference": "Patient/p", "type": "Practitioner"},
                    )
                ]
            )
        ]
    )
    result = run(server)
    assert result["summary"]["outcomes"] == {
        "unresolvable_invalid": 1,
        "unresolvable_type_mismatch": 1,
    }
    assert result["unique_target_lookups"] == 0
    assert result["summary"]["sources_with_broken_reference"]["numerator"] == 0
    assert result["summary"]["sources_with_resolution_problem"]["numerator"] == 1


def test_malformed_reference_array_is_visible_in_consumer_problem_rate():
    result = run(SearchServer([page([source(supportingInfo="invalid")])]))
    assert result["inventory_issues"]
    assert result["sources"][0]["has_resolution_problem"]
    assert result["summary"]["http_resolution_rate"]["denominator"] == 0
    malformed = run(
        SearchServer(
            [
                page(
                    [
                        source(
                            subject={"reference": "#bad"},
                            contained=[{"resourceType": {}, "id": "bad"}],
                        )
                    ]
                )
            ]
        )
    )
    assert malformed["inventory_issues"]
    assert malformed["summary"]["outcomes"] == {"missing_contained": 1}


def test_reusing_runner_does_not_reuse_results_from_a_previous_run():
    server = SearchServer([page([source(subject={"reference": "Patient/p"})])] * 2)
    server.resources["Patient/p"] = {"resourceType": "Patient", "id": "p"}
    runner = IntegrityRun(make_client(server), min_interval=0)
    assert runner.run("ServiceRequest", 1)["summary"]["outcomes"] == {"resolved_200": 1}
    server.faults[("GET", "/fhir/Patient/p")].append(410)
    second = runner.run("ServiceRequest", 1)
    assert second["summary"]["outcomes"] == {"gone_410": 1}
    assert second["cache_hits"] == 0 and second["unique_target_lookups"] == 1


def test_reservoir_is_scattered_repeatable_and_independent_of_page_boundaries():
    resources = [source(f"private-{i}") for i in range(100)]

    def measure(width):
        pages = [
            page(
                resources[i : i + width],
                f"https://fhir.test/fhir/ServiceRequest?page={i + width}"
                if i + width < 100
                else None,
            )
            for i in range(0, 100, width)
        ]
        return IntegrityRun(make_client(SearchServer(pages)), min_interval=0).run(
            "ServiceRequest", 10, sampling_method="reservoir", skip=5, seed=42
        )

    a, b = measure(10), measure(25)
    positions = a["sampling"]["selected_stream_positions"]
    assert positions == b["sampling"]["selected_stream_positions"]
    assert len(positions) == len(set(positions)) == 10
    assert min(positions) > 5 and max(positions) > 70
    assert len({(p - 1) // 10 for p in positions}) > 3
    assert a["sampling"]["eligible_sources"] == 95
    assert a["sampling"]["population_exhausted"] and a["sampling"]["complete"]
    assert "private-" not in json.dumps(a)


def test_reservoir_short_population_keeps_actual_denominator():
    result = IntegrityRun(
        make_client(SearchServer([page([source(str(i)) for i in range(30)])])),
        min_interval=0,
    ).run("ServiceRequest", 100, sampling_method="reservoir", skip=10)
    assert result["sampled_resources"] == 20
    assert result["summary"]["sources_with_broken_reference"]["denominator"] == 20
    assert result["sampling"]["population_exhausted"]
    assert not result["sampling"]["complete"]


def test_reservoir_scan_limit_does_not_claim_population_exhaustion():
    result = IntegrityRun(
        make_client(SearchServer([page([source(str(i)) for i in range(20)])])),
        min_interval=0,
    ).run("ServiceRequest", 5, sampling_method="reservoir", max_scan=10)
    assert result["sampling"]["stop_reason"] == "scan_limit_reached"
    assert not result["sampling"]["population_exhausted"]
    assert result["sampling"]["scanned_unique_sources"] == 10


def test_cluster_statistics_distinguish_shared_targets_from_occurrences():
    resources = [
        source(
            str(i),
            subject={"reference": "Patient/shared"},
            requester={"reference": "Practitioner/shared"},
            supportingInfo=[{"reference": "Patient/shared"}],
        )
        for i in range(3)
    ]
    result = run(SearchServer([page(resources)]))
    assert result["summary"]["unique_http_broken_targets"] == 2
    assert result["summary"]["known_broken_references"] == 9
    assert result["clustering"]["shared_broken_target_sets"][0]["source_count"] == 3
    patient = next(
        x
        for x in result["clustering"]["broken_target_fanout"]
        if x["target"].startswith("Patient/")
    )
    assert patient["source_count"] == 3 and patient["reference_occurrences"] == 6
    text = render_report(result)
    assert text.index("Distinct-target resolution") < text.index(
        "Occurrence resolution"
    )
    assert "same **2 distinct targets**" in text
