from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Sequence

from src.fhir_client import (
    FHIRClient,
    FHIRNotFoundError,
    FHIRReferenceError,
    FetchedResource,
)
from src.models import InputProvenance, ResourceProvenance


_FHIR_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
_BUNDLE_ID_HASH_LENGTH = 12
_BUNDLE_ID_PREFIX = "live-"


@dataclass(frozen=True)
class AssemblyIssue:
    """A reference that could not be safely added to the assembled Bundle."""

    field: str
    reference: str | None
    reason: str
    detail: str = ""

    @property
    def field_path(self) -> str:
        """Compatibility alias for callers that prefer an explicit path name."""

        return self.field

    def to_dict(self) -> dict[str, str | None]:
        return {
            "field": self.field,
            "reference": self.reference,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BundleAssemblyResult:
    bundle: dict[str, Any]
    input_provenance: InputProvenance
    issues: list[AssemblyIssue]


class BundleAssemblyError(ValueError):
    """Raised when the root ServiceRequest cannot form a valid parser input."""


@dataclass(frozen=True)
class _ExternalResolution:
    fetched: FetchedResource | None
    reason: str = ""
    detail: str = ""


class BundleAssembler:
    """Fetch the narrow resource graph consumed by the existing parser."""

    def __init__(self, client: FHIRClient) -> None:
        self.client = client

    def assemble(self, service_request_id: str) -> BundleAssemblyResult:
        fetched_service_request = self.client.get_resource(
            "ServiceRequest",
            service_request_id,
        )
        service_request = self._validated_root_resource(fetched_service_request)
        assembled_service_request = deepcopy(service_request)

        entries: list[dict[str, Any]] = []
        entry_keys: set[str] = set()
        issues: list[AssemblyIssue] = []
        fetched_cache: dict[str, _ExternalResolution] = {}
        provenance: list[ResourceProvenance] = []
        provenance_keys: set[tuple[str, str]] = set()

        self._record_provenance(
            fetched_service_request,
            provenance,
            provenance_keys,
        )

        self._resolve_single_field(
            assembled_service_request,
            "subject",
            ("Patient",),
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )
        self._resolve_single_field(
            assembled_service_request,
            "requester",
            ("Practitioner",),
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )
        self._resolve_single_field(
            assembled_service_request,
            "encounter",
            ("Encounter",),
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )
        self._resolve_list_field(
            assembled_service_request,
            "reasonReference",
            ("Condition",),
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )
        self._resolve_list_field(
            assembled_service_request,
            "supportingInfo",
            ("Observation", "DocumentReference"),
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )

        service_request_key = self._resource_key(assembled_service_request)
        if service_request_key is None:
            # The root was validated above, so reaching this branch would indicate
            # accidental mutation inside the assembler rather than untrusted input.
            raise BundleAssemblyError(
                "The fetched ServiceRequest lost its valid resourceType or id during assembly."
            )
        entries.append(
            {
                "fullUrl": service_request_key,
                "resource": assembled_service_request,
            }
        )

        server_base_url = fetched_service_request.provenance.server_base_url
        fetched_at = fetched_service_request.provenance.fetched_at
        if not isinstance(fetched_at, str) or not fetched_at.strip():
            raise BundleAssemblyError(
                "The fetched ServiceRequest provenance must include a fetch timestamp."
            )

        bundle = {
            "resourceType": "Bundle",
            "id": _make_bundle_id(server_base_url, service_request["id"]),
            "type": "collection",
            "timestamp": fetched_at,
            "entry": entries,
        }
        return BundleAssemblyResult(
            bundle=bundle,
            input_provenance=InputProvenance(
                source_type="live",
                resources=provenance,
                scope_notes=_assembly_scope_notes(service_request),
            ),
            issues=issues,
        )

    def _validated_root_resource(
        self,
        fetched: FetchedResource,
    ) -> dict[str, Any]:
        resource = fetched.resource
        if not isinstance(resource, dict):
            raise BundleAssemblyError(
                "The ServiceRequest endpoint returned a non-object payload."
            )
        if resource.get("resourceType") != "ServiceRequest":
            raise BundleAssemblyError(
                "The ServiceRequest endpoint returned an unexpected resource type."
            )
        resource_id = resource.get("id")
        if not _is_valid_fhir_id(resource_id):
            raise BundleAssemblyError(
                "The fetched ServiceRequest must contain a valid FHIR id."
            )
        return resource

    def _resolve_single_field(
        self,
        service_request: dict[str, Any],
        field_name: str,
        expected_types: tuple[str, ...],
        entries: list[dict[str, Any]],
        entry_keys: set[str],
        provenance: list[ResourceProvenance],
        provenance_keys: set[tuple[str, str]],
        fetched_cache: dict[str, _ExternalResolution],
        issues: list[AssemblyIssue],
    ) -> None:
        if field_name not in service_request:
            return
        self._resolve_reference_value(
            service_request,
            field_name,
            service_request.get(field_name),
            expected_types,
            entries,
            entry_keys,
            provenance,
            provenance_keys,
            fetched_cache,
            issues,
        )

    def _resolve_list_field(
        self,
        service_request: dict[str, Any],
        field_name: str,
        expected_types: tuple[str, ...],
        entries: list[dict[str, Any]],
        entry_keys: set[str],
        provenance: list[ResourceProvenance],
        provenance_keys: set[tuple[str, str]],
        fetched_cache: dict[str, _ExternalResolution],
        issues: list[AssemblyIssue],
    ) -> None:
        if field_name not in service_request:
            return
        values = service_request.get(field_name)
        if not isinstance(values, list):
            issues.append(
                AssemblyIssue(
                    field=field_name,
                    reference=None,
                    reason="invalid_reference_shape",
                    detail="Expected a list of FHIR Reference objects.",
                )
            )
            return

        for index, value in enumerate(values):
            self._resolve_reference_value(
                service_request,
                f"{field_name}[{index}]",
                value,
                expected_types,
                entries,
                entry_keys,
                provenance,
                provenance_keys,
                fetched_cache,
                issues,
            )

    def _resolve_reference_value(
        self,
        service_request: dict[str, Any],
        field_path: str,
        reference_value: Any,
        expected_types: tuple[str, ...],
        entries: list[dict[str, Any]],
        entry_keys: set[str],
        provenance: list[ResourceProvenance],
        provenance_keys: set[tuple[str, str]],
        fetched_cache: dict[str, _ExternalResolution],
        issues: list[AssemblyIssue],
    ) -> None:
        if not isinstance(reference_value, dict):
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=None,
                    reason="invalid_reference_shape",
                    detail="Expected a FHIR Reference object.",
                )
            )
            return

        raw_reference = reference_value.get("reference")
        if (
            not isinstance(raw_reference, str)
            or not raw_reference
            or raw_reference != raw_reference.strip()
        ):
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=raw_reference if isinstance(raw_reference, str) else None,
                    reason="invalid_reference",
                    detail="Reference must be a non-empty string without outer whitespace.",
                )
            )
            return

        if raw_reference.startswith("#"):
            self._resolve_contained_reference(
                service_request,
                field_path,
                raw_reference,
                expected_types,
                entries,
                entry_keys,
                issues,
            )
            return

        resolution = fetched_cache.get(raw_reference)
        if resolution is None:
            resolution = self._fetch_reference(raw_reference, expected_types)
            fetched_cache[raw_reference] = resolution
            if resolution.fetched is not None:
                self._record_provenance(
                    resolution.fetched,
                    provenance,
                    provenance_keys,
                )
                canonical_key = self._resource_key(resolution.fetched.resource)
                if canonical_key is not None:
                    fetched_cache.setdefault(canonical_key, resolution)

        if resolution.fetched is None:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=raw_reference,
                    reason=resolution.reason,
                    detail=resolution.detail,
                )
            )
            return

        resource = resolution.fetched.resource
        resource_key = self._resource_key(resource)
        if resource_key is None:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=raw_reference,
                    reason="invalid_fetched_resource",
                    detail="Fetched resource must have a valid resourceType and FHIR id.",
                )
            )
            return

        resource_type = resource.get("resourceType")
        if resource_type not in expected_types:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=raw_reference,
                    reason="fetched_type_mismatch",
                    detail=(
                        f"Expected {_format_expected_types(expected_types)}; "
                        f"received {resource_type}."
                    ),
                )
            )
            return

        self._add_entry(
            resource,
            resource_key,
            entries,
            entry_keys,
        )
        # Only references backed by a successfully validated external fetch are
        # rewritten. Failed and malformed source references remain untouched.
        reference_value["reference"] = resource_key

    def _fetch_reference(
        self,
        reference: str,
        expected_types: tuple[str, ...],
    ) -> _ExternalResolution:
        try:
            fetched = self.client.get_reference(reference, expected_types)
        # A missing/unsafe source reference remains a data-quality issue. Auth,
        # transport, server and response-shape failures abort assembly so they
        # cannot be misrepresented as missing clinical information.
        except (FHIRNotFoundError, FHIRReferenceError) as exc:
            exception_name = type(exc).__name__
            reason = (
                "invalid_reference" if "Reference" in exception_name else "fetch_failed"
            )
            status_code = getattr(exc, "status_code", None)
            detail = exception_name
            if isinstance(status_code, int):
                detail = f"{detail} (HTTP {status_code})"
            return _ExternalResolution(
                fetched=None,
                reason=reason,
                detail=detail,
            )

        if not isinstance(fetched, FetchedResource):
            return _ExternalResolution(
                fetched=None,
                reason="invalid_fetched_resource",
                detail="FHIR client returned an invalid fetch result.",
            )
        return _ExternalResolution(fetched=fetched)

    def _resolve_contained_reference(
        self,
        service_request: dict[str, Any],
        field_path: str,
        reference: str,
        expected_types: tuple[str, ...],
        entries: list[dict[str, Any]],
        entry_keys: set[str],
        issues: list[AssemblyIssue],
    ) -> None:
        contained_id = reference[1:]
        if not _is_valid_fhir_id(contained_id):
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="invalid_reference",
                    detail="Contained reference must use # followed by a valid FHIR id.",
                )
            )
            return

        contained = service_request.get("contained")
        if not isinstance(contained, list):
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="contained_not_found",
                    detail="ServiceRequest does not contain the referenced resource.",
                )
            )
            return

        matches = [
            resource
            for resource in contained
            if isinstance(resource, dict) and resource.get("id") == contained_id
        ]
        if not matches:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="contained_not_found",
                    detail="ServiceRequest does not contain the referenced resource.",
                )
            )
            return
        if len(matches) > 1:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="duplicate_contained_id",
                    detail="Multiple contained resources use the referenced id.",
                )
            )
            return

        resource = matches[0]
        resource_type = resource.get("resourceType")
        if resource_type not in expected_types:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="contained_type_mismatch",
                    detail=(
                        f"Expected {_format_expected_types(expected_types)}; "
                        f"received {resource_type or 'no resourceType'}."
                    ),
                )
            )
            return

        if self._resource_key(resource) is None:
            issues.append(
                AssemblyIssue(
                    field=field_path,
                    reference=reference,
                    reason="invalid_contained_resource",
                    detail=(
                        "Contained resource must include a supported resourceType "
                        "and a valid FHIR id."
                    ),
                )
            )
            return

        self._add_entry(resource, reference, entries, entry_keys)

    @staticmethod
    def _add_entry(
        resource: dict[str, Any],
        full_url: str,
        entries: list[dict[str, Any]],
        entry_keys: set[str],
    ) -> None:
        resource_key = BundleAssembler._resource_key(resource)
        if resource_key is None or resource_key in entry_keys:
            return
        entries.append(
            {
                "fullUrl": full_url,
                "resource": deepcopy(resource),
            }
        )
        entry_keys.add(resource_key)

    @staticmethod
    def _record_provenance(
        fetched: FetchedResource,
        provenance: list[ResourceProvenance],
        provenance_keys: set[tuple[str, str]],
    ) -> None:
        item = fetched.provenance
        key = (item.resource_type, item.resource_id)
        if key in provenance_keys:
            return
        provenance.append(item)
        provenance_keys.add(key)

    @staticmethod
    def _resource_key(resource: Any) -> str | None:
        if not isinstance(resource, dict):
            return None
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if not isinstance(resource_type, str) or not resource_type:
            return None
        if not _is_valid_fhir_id(resource_id):
            return None
        return f"{resource_type}/{resource_id}"


def assemble_service_request_bundle(
    service_request_id: str,
    *,
    client: FHIRClient | None = None,
    base_url: str | None = None,
) -> BundleAssemblyResult:
    """Convenience entry point for assembling one live ServiceRequest graph."""

    if client is not None and base_url is not None:
        raise ValueError("Pass either client or base_url, not both.")
    resolved_client = client
    if resolved_client is None:
        resolved_client = (
            FHIRClient(base_url=base_url) if base_url is not None else FHIRClient()
        )
    return BundleAssembler(resolved_client).assemble(service_request_id)


def assemble_bundle(
    service_request_id: str,
    *,
    client: FHIRClient | None = None,
    base_url: str | None = None,
) -> BundleAssemblyResult:
    """Short alias for :func:`assemble_service_request_bundle`."""

    return assemble_service_request_bundle(
        service_request_id,
        client=client,
        base_url=base_url,
    )


def _is_valid_fhir_id(value: Any) -> bool:
    return isinstance(value, str) and _FHIR_ID_PATTERN.fullmatch(value) is not None


def _make_bundle_id(server_base_url: str, service_request_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9\-.]+", "-", service_request_id).strip("-.")
    if not safe_id:
        safe_id = "servicerequest"
    digest = hashlib.sha256(
        f"{server_base_url}|{service_request_id}".encode("utf-8")
    ).hexdigest()[:_BUNDLE_ID_HASH_LENGTH]
    max_safe_id_length = 64 - len(_BUNDLE_ID_PREFIX) - len(digest) - 1
    safe_id = safe_id[:max_safe_id_length].rstrip("-.") or "servicerequest"
    return f"{_BUNDLE_ID_PREFIX}{safe_id}-{digest}"


def _format_expected_types(expected_types: Sequence[str]) -> str:
    if len(expected_types) == 1:
        return expected_types[0]
    return " or ".join(expected_types)


def _assembly_scope_notes(service_request: dict[str, Any]) -> list[str]:
    notes = [
        "Reverse references to this ServiceRequest were not searched or assembled."
    ]
    assembled_fields = {
        "subject",
        "requester",
        "encounter",
        "reasonReference",
        "supportingInfo",
    }
    for field_name, value in service_request.items():
        if field_name in assembled_fields or field_name == "contained":
            continue
        for reference_path in _reference_paths(value, field_name):
            notes.append(
                f"Ignored out-of-scope reference at ServiceRequest.{reference_path}."
            )
    return notes


def _reference_paths(value: Any, path: str) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "reference" and isinstance(child, str) and child.strip():
                paths.append(child_path)
            else:
                paths.extend(_reference_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_reference_paths(child, f"{path}[{index}]"))
    return paths


__all__ = [
    "AssemblyIssue",
    "BundleAssembler",
    "BundleAssemblyError",
    "BundleAssemblyResult",
    "assemble_bundle",
    "assemble_service_request_bundle",
]
