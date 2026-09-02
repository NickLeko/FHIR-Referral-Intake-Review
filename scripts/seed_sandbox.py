from __future__ import annotations

import argparse
import hashlib
import re
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fhir_client import FHIRClient, FHIRClientError, FHIR_JSON_MEDIA_TYPE
from src.utils import DATA_DIR, list_sample_bundle_paths, load_json_file


class SandboxSeedError(RuntimeError):
    """A synthetic transaction could not be safely submitted or interpreted."""


class SandboxSeeder:
    """POST synthetic transaction Bundles without retrying non-idempotent writes."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 20.0,
        session: Any | None = None,
    ) -> None:
        self._session = session if session is not None else requests.Session()
        configuration = FHIRClient(
            base_url=base_url,
            timeout=timeout,
            session=self._session,
        )
        self.base_url = configuration.base_url
        self.timeout = configuration.timeout
        self.user_agent = configuration.user_agent

    def seed_bundle(self, source_bundle: dict[str, Any]) -> str:
        transaction, service_request_index = build_transaction_bundle(source_bundle)
        headers = {
            "Accept": FHIR_JSON_MEDIA_TYPE,
            "Content-Type": FHIR_JSON_MEDIA_TYPE,
            "User-Agent": self.user_agent,
            "Prefer": "return=minimal",
        }
        try:
            response = self._session.post(
                self.base_url,
                json=transaction,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise SandboxSeedError("Sandbox transaction request failed.") from exc

        try:
            status_code = getattr(response, "status_code", None)
            if not isinstance(status_code, int) or not 200 <= status_code < 300:
                status_label = status_code if isinstance(status_code, int) else "unknown"
                raise SandboxSeedError(
                    f"Sandbox transaction returned HTTP {status_label}."
                )
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise SandboxSeedError(
                    "Sandbox transaction response was not valid JSON."
                ) from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

        return _service_request_id_from_response(payload, service_request_index)


def build_transaction_bundle(
    source_bundle: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Convert one checked-in collection Bundle into a create transaction."""

    if not isinstance(source_bundle, dict) or source_bundle.get("resourceType") != "Bundle":
        raise SandboxSeedError("Seed input must be a FHIR Bundle object.")
    entries = source_bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        raise SandboxSeedError("Seed Bundle must contain entries.")

    bundle_id = source_bundle.get("id")
    bundle_label = bundle_id if isinstance(bundle_id, str) and bundle_id else "seed-bundle"
    alias_by_reference: dict[str, str] = {}
    prepared: list[tuple[str, dict[str, Any]]] = []
    service_request_indices: list[int] = []

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
            raise SandboxSeedError(f"Seed Bundle entry {index} has no resource object.")
        resource = entry["resource"]
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if not isinstance(resource_type, str) or not resource_type:
            raise SandboxSeedError(
                f"Seed Bundle entry {index} has no valid resourceType."
            )
        if not isinstance(resource_id, str) or not resource_id:
            raise SandboxSeedError(f"Seed Bundle entry {index} has no valid id.")
        canonical_reference = f"{resource_type}/{resource_id}"
        if canonical_reference in alias_by_reference:
            raise SandboxSeedError(
                f"Seed Bundle contains duplicate resource {canonical_reference}."
            )
        generated_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{bundle_label}/{index}/{canonical_reference}",
        )
        full_url = f"urn:uuid:{generated_id}"
        alias_by_reference[canonical_reference] = full_url
        prepared.append((full_url, resource))
        if resource_type == "ServiceRequest":
            service_request_indices.append(index)

    if len(service_request_indices) != 1:
        raise SandboxSeedError(
            "Each seed Bundle must contain exactly one ServiceRequest."
        )

    transaction_entries: list[dict[str, Any]] = []
    for full_url, original_resource in prepared:
        resource = deepcopy(original_resource)
        resource.pop("id", None)
        _rewrite_internal_references(resource, alias_by_reference, bundle_label)
        transaction_entries.append(
            {
                "fullUrl": full_url,
                "resource": resource,
                "request": {
                    "method": "POST",
                    "url": original_resource["resourceType"],
                },
            }
        )

    return (
        {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": transaction_entries,
        },
        service_request_indices[0],
    )


def seed_all_sample_bundles(
    seeder: SandboxSeeder,
    *,
    data_dir: Path | None = None,
) -> list[tuple[str, str]]:
    data_dir = Path(data_dir) if data_dir is not None else PROJECT_ROOT / DATA_DIR
    bundle_paths = list_sample_bundle_paths(data_dir)
    if len(bundle_paths) != 7:
        raise SandboxSeedError(
            f"Expected seven checked-in sample Bundles; found {len(bundle_paths)}."
        )
    results: list[tuple[str, str]] = []
    for bundle_path in bundle_paths:
        source_bundle = load_json_file(bundle_path)
        service_request_id = seeder.seed_bundle(source_bundle)
        results.append((bundle_path.name, service_request_id))
    return results


def _rewrite_internal_references(
    value: Any,
    aliases: dict[str, str],
    bundle_label: str,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "reference" and isinstance(child, str) and child in aliases:
                value[key] = aliases[child]
            elif key == "reference" and isinstance(child, str):
                match = re.fullmatch(
                    r"(?P<resource_type>[A-Z][A-Za-z0-9]*)/"
                    r"[A-Za-z0-9.-]{1,64}",
                    child,
                )
                if match:
                    digest = hashlib.sha256(
                        f"{bundle_label}|{child}".encode("utf-8")
                    ).hexdigest()[:20]
                    value[key] = (
                        f"{match.group('resource_type')}/codex-missing-{digest}"
                    )
            else:
                _rewrite_internal_references(child, aliases, bundle_label)
    elif isinstance(value, list):
        for child in value:
            _rewrite_internal_references(child, aliases, bundle_label)


def _service_request_id_from_response(payload: Any, entry_index: int) -> str:
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise SandboxSeedError("Sandbox response was not a FHIR Bundle.")
    if payload.get("type") != "transaction-response":
        raise SandboxSeedError("Sandbox response was not a transaction response.")
    entries = payload.get("entry")
    if not isinstance(entries, list) or entry_index >= len(entries):
        raise SandboxSeedError("Sandbox response omitted the ServiceRequest result.")
    entry = entries[entry_index]
    if not isinstance(entry, dict):
        raise SandboxSeedError("Sandbox ServiceRequest response entry was malformed.")

    response_block = entry.get("response")
    location = response_block.get("location") if isinstance(response_block, dict) else None
    if isinstance(location, str):
        path_parts = location.split("?", 1)[0].rstrip("/").split("/")
        for index, part in enumerate(path_parts[:-1]):
            if part == "ServiceRequest":
                resource_id = path_parts[index + 1]
                if _is_valid_fhir_id(resource_id):
                    return resource_id

    resource = entry.get("resource")
    if isinstance(resource, dict) and resource.get("resourceType") == "ServiceRequest":
        resource_id = resource.get("id")
        if _is_valid_fhir_id(resource_id):
            return resource_id
    raise SandboxSeedError("Sandbox response did not identify the new ServiceRequest.")


def _is_valid_fhir_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9.-]{1,64}", value) is not None
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="POST the seven checked-in synthetic Bundles as FHIR transactions.",
        epilog=(
            "The public HAPI sandbox is periodically wiped. Returned resource IDs "
            "are temporary and are not stable demo identifiers."
        ),
    )
    parser.add_argument(
        "--base-url",
        help="FHIR R4 server base URL (defaults to FHIR_BASE_URL or public HAPI).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        seeder = SandboxSeeder(base_url=args.base_url)
        results = seed_all_sample_bundles(seeder)
    except (FHIRClientError, SandboxSeedError, ValueError) as error:
        print(f"Unable to seed sandbox: {error}", file=sys.stderr)
        return 1

    print("Public sandbox IDs are temporary; the server is periodically wiped.")
    for bundle_name, service_request_id in results:
        print(f"{bundle_name}: {service_request_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
