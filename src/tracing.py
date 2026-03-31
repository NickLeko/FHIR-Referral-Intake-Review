from __future__ import annotations

from typing import Any

from src.models import TraceEntry


def make_trace(resource: dict[str, Any], field_path: str) -> TraceEntry:
    return TraceEntry(
        resource_type=resource["resourceType"],
        resource_id=resource["id"],
        field_path=field_path,
    )


def add_trace(
    trace_map: dict[str, list[TraceEntry]],
    field_name: str,
    *entries: TraceEntry | None,
) -> None:
    bucket = trace_map.setdefault(field_name, [])
    seen = {(entry.resource_type, entry.resource_id, entry.field_path) for entry in bucket}
    for entry in entries:
        if entry is None:
            continue
        key = (entry.resource_type, entry.resource_id, entry.field_path)
        if key in seen:
            continue
        bucket.append(entry)
        seen.add(key)
