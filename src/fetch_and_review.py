from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from src.bundle_assembler import BundleAssembler, BundleAssemblyError
from src.fhir_client import FHIRClient, FHIRClientError
from src.mapping import build_review_packet
from src.parser import BundleValidationError, parse_bundle
from src.utils import save_json_file

LIVE_OUTPUT_DIR = Path("outputs/live")


def fetch_and_review(
    service_request_id: str,
    *,
    base_url: str | None = None,
    output_dir: Path = LIVE_OUTPUT_DIR,
    client: Any | None = None,
) -> Path:
    """Fetch one ServiceRequest, run the deterministic review, and save its packet."""
    if not isinstance(service_request_id, str):
        raise ValueError("service_request_id must be a string.")
    service_request_id = service_request_id.strip()
    if not service_request_id:
        raise ValueError("service_request_id is required.")

    if client is None:
        client = FHIRClient(base_url=base_url) if base_url is not None else FHIRClient()

    packet = fetch_review_packet(service_request_id, client=client)

    output_path = Path(output_dir) / _output_filename(service_request_id)
    save_json_file(output_path, packet.to_dict())
    return output_path


def fetch_review_packet(service_request_id: str, *, client: FHIRClient):
    assembly_result = BundleAssembler(client).assemble(service_request_id)
    parsed_bundle = parse_bundle(assembly_result.bundle)
    parsed_bundle.input_provenance = assembly_result.input_provenance
    try:
        return build_review_packet(parsed_bundle)
    except (AttributeError, TypeError, IndexError, KeyError):
        raise BundleValidationError(
            "Fetched resources violate the supported field shape; human investigation required."
        ) from None


def _output_filename(service_request_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", service_request_id.strip())
    safe_id = safe_id.strip(".-_")[:80] or "service-request"
    return f"{safe_id}_review_packet.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a FHIR R4 ServiceRequest and save its deterministic referral "
            "intake review packet."
        )
    )
    parser.add_argument(
        "--service-request",
        required=True,
        action="append",
        help="FHIR ServiceRequest resource id to fetch; repeat for independent packets.",
    )
    parser.add_argument(
        "--base-url",
        help="FHIR R4 server base URL (defaults to FHIR_BASE_URL or the client default).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        client = FHIRClient(base_url=args.base_url)
        results = fetch_batch(args.service_request, client=client)
    except FHIRClientError as error:
        print(f"Unable to configure FHIR access: {error}", file=sys.stderr)
        return 1
    for result in results:
        print(result)
    return 0 if all(r["state"] == "awaiting_review" for r in results) else 1


def fetch_batch(service_request_ids, *, client, output_dir=LIVE_OUTPUT_DIR):
    results = []
    for source_id in service_request_ids:
        try:
            path = fetch_and_review(source_id, client=client, output_dir=output_dir)
            results.append(
                {
                    "service_request_id": source_id,
                    "state": "awaiting_review",
                    "path": str(path),
                }
            )
        except (
            FHIRClientError,
            BundleAssemblyError,
            BundleValidationError,
            ValueError,
        ) as error:
            results.append(
                {
                    "service_request_id": source_id,
                    "state": "needs_attention",
                    "reason": type(error).__name__,
                }
            )
    save_json_file(Path(output_dir) / "fetch_batch.json", {"results": results})
    return results


if __name__ == "__main__":
    raise SystemExit(main())
