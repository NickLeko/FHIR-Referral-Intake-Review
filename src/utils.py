from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path("data/sample_bundles")
OUTPUT_DIR = Path("outputs")


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def list_sample_bundle_paths(data_dir: Path = DATA_DIR) -> list[Path]:
    return sorted(data_dir.glob("*.json"))


def sample_output_path(bundle_path: Path, output_dir: Path = OUTPUT_DIR) -> Path:
    parts = bundle_path.stem.split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else bundle_path.stem
    return output_dir / f"{prefix}_output.json"


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def join_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        if cleaned is None or cleaned in seen:
            continue
        result.append(cleaned)
        seen.add(cleaned)
    return result


def extract_codeable_concept_text(concept: dict[str, Any] | None) -> str | None:
    if not isinstance(concept, dict):
        return None

    text_value = clean_text(concept.get("text"))
    if text_value:
        return text_value

    coding = concept.get("coding")
    if not isinstance(coding, list):
        return None

    for item in coding:
        if not isinstance(item, dict):
            continue
        display = clean_text(item.get("display"))
        if display:
            return display
        code = clean_text(item.get("code"))
        if code:
            return code
    return None


def extract_human_name(name_block: dict[str, Any] | None) -> str | None:
    if not isinstance(name_block, dict):
        return None

    text_value = clean_text(name_block.get("text"))
    if text_value:
        return text_value

    given = name_block.get("given")
    family = clean_text(name_block.get("family"))
    pieces: list[str] = []
    if isinstance(given, list):
        pieces.extend(clean_text(part) for part in given if clean_text(part))
    if family:
        pieces.append(family)
    return clean_text(" ".join(pieces))


def age_group_from_birth_date(
    birth_date_text: str | None,
    reference_date: date | None = None,
) -> str | None:
    if birth_date_text is None:
        return None

    try:
        birth_date = date.fromisoformat(birth_date_text)
    except ValueError:
        return None

    today = reference_date or date.today()
    age_years = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )

    if age_years < 18:
        return "Pediatric"
    if age_years < 65:
        return "Adult"
    return "Older adult"


def summarize_condition(condition: dict[str, Any]) -> str | None:
    code = condition.get("code")
    display_text = extract_codeable_concept_text(code)
    coding = code.get("coding") if isinstance(code, dict) else None
    code_value: str | None = None
    if isinstance(coding, list):
        for item in coding:
            if not isinstance(item, dict):
                continue
            code_value = clean_text(item.get("code"))
            if code_value:
                break
    if code_value and display_text:
        return f"{code_value} - {display_text}"
    return display_text


def summarize_observation_value(observation: dict[str, Any]) -> str | None:
    quantity = observation.get("valueQuantity")
    if isinstance(quantity, dict):
        value = quantity.get("value")
        unit = clean_text(quantity.get("unit")) or clean_text(quantity.get("code"))
        if value is not None and unit:
            return f"{value} {unit}"
        if value is not None:
            return str(value)

    text_value = clean_text(observation.get("valueString"))
    if text_value:
        return text_value

    concept_value = extract_codeable_concept_text(observation.get("valueCodeableConcept"))
    if concept_value:
        return concept_value

    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
