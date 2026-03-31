from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.models import ParsedBundle

SUPPORTED_RESOURCE_TYPES = {
    "Patient",
    "ServiceRequest",
    "Practitioner",
    "Condition",
    "Encounter",
    "Observation",
    "DocumentReference",
}


class BundleValidationError(ValueError):
    """Raised when a mock FHIR bundle cannot be safely processed."""


def parse_bundle(bundle_data: dict[str, Any]) -> ParsedBundle:
    if bundle_data.get("resourceType") != "Bundle":
        raise BundleValidationError("Input must be a FHIR Bundle resource.")

    bundle_id = bundle_data.get("id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise BundleValidationError("Bundle id is required.")

    entries = bundle_data.get("entry")
    if not isinstance(entries, list) or not entries:
        raise BundleValidationError("Bundle must contain at least one entry.")

    resources_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    resources_by_reference: dict[str, dict[str, Any]] = {}
    unsupported_resources: list[dict[str, str]] = []

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BundleValidationError(f"Bundle entry {index} must be an object.")

        resource = entry.get("resource")
        if not isinstance(resource, dict):
            raise BundleValidationError(f"Bundle entry {index} is missing a resource object.")

        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if not isinstance(resource_type, str) or not isinstance(resource_id, str):
            raise BundleValidationError(
                f"Bundle entry {index} must include resourceType and id."
            )

        if resource_type not in SUPPORTED_RESOURCE_TYPES:
            unsupported_resources.append(
                {"resource_type": resource_type, "resource_id": resource_id}
            )
            continue

        resources_by_type[resource_type].append(resource)
        resources_by_reference[f"{resource_type}/{resource_id}"] = resource

    if not resources_by_type.get("ServiceRequest"):
        raise BundleValidationError("Bundle must include at least one ServiceRequest.")

    return ParsedBundle(
        bundle_id=bundle_id,
        raw_bundle=bundle_data,
        resources_by_type=dict(resources_by_type),
        resources_by_reference=resources_by_reference,
        unsupported_resources=unsupported_resources,
    )


def get_resources(parsed_bundle: ParsedBundle, resource_type: str) -> list[dict[str, Any]]:
    return parsed_bundle.resources_by_type.get(resource_type, [])


def get_first_resource(parsed_bundle: ParsedBundle, resource_type: str) -> dict[str, Any] | None:
    resources = get_resources(parsed_bundle, resource_type)
    return resources[0] if resources else None


def resolve_reference(
    parsed_bundle: ParsedBundle,
    reference: str | None,
) -> dict[str, Any] | None:
    if reference is None:
        return None
    return parsed_bundle.resources_by_reference.get(reference)
