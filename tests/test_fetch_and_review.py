from __future__ import annotations

from pathlib import Path

from src.bundle_assembler import BundleAssemblyResult
from src.fetch_and_review import fetch_and_review
from src.models import InputProvenance, ResourceProvenance
from src.utils import load_json_file


class FakeAssembler:
    def __init__(self, _client) -> None:
        pass

    def assemble(self, _service_request_id: str) -> BundleAssemblyResult:
        return BundleAssemblyResult(
            bundle=load_json_file(Path("data/sample_bundles/bundle_001_review_ready.json")),
            input_provenance=InputProvenance(
                source_type="live",
                resources=[
                    ResourceProvenance(
                        server_base_url="https://example.test/fhir",
                        resource_type="ServiceRequest",
                        resource_id="sr-001",
                        version_id="1",
                        last_updated="2026-08-20T12:00:00Z",
                        fetched_at="2026-08-20T12:01:00+00:00",
                    )
                ],
            ),
            issues=[],
        )


def test_fetch_and_review_writes_an_unreviewed_live_packet_offline(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("src.fetch_and_review.BundleAssembler", FakeAssembler)

    output_path = fetch_and_review(
        "sr-001",
        client=object(),
        output_dir=tmp_path,
    )
    payload = load_json_file(output_path)

    assert output_path == tmp_path / "sr-001_review_packet.json"
    assert payload["status"] == "REVIEW_READY"
    assert payload["input_provenance"]["source_type"] == "live"
    assert payload["input_provenance"]["resources"][0]["resource_id"] == "sr-001"
    assert "human_review_decision" not in payload
