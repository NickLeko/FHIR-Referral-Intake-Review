from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path("data/sample_bundles")
OUTPUT_DIR = Path("outputs")
REVIEW_HISTORY_DIR = OUTPUT_DIR / "review_history"


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


def _bundle_output_prefix(bundle_path: Path) -> str:
    parts = bundle_path.stem.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else bundle_path.stem


def sample_output_path(
    bundle_path: Path,
    artifact_label: str | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    prefix = _bundle_output_prefix(bundle_path)
    if artifact_label is None:
        return output_dir / f"{prefix}_output.json"
    return output_dir / f"{prefix}_{artifact_label}_output.json"


def review_history_output_path(
    bundle_path: Path,
    reviewed_at: str,
    decision: str,
    output_dir: Path = REVIEW_HISTORY_DIR,
) -> Path:
    safe_reviewed_at = reviewed_at.replace(":", "-")
    decision_label = decision.lower()
    bundle_label = bundle_path.stem
    return (
        output_dir
        / bundle_label
        / f"{bundle_label}__{safe_reviewed_at}__{decision_label}.json"
    )


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
    if birth_date_text is None or reference_date is None:
        return None

    birth_date = parse_date_value(birth_date_text)
    if birth_date is None:
        return None

    age_years = reference_date.year - birth_date.year - (
        (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day)
    )

    if age_years < 18:
        return "Pediatric"
    if age_years < 65:
        return "Adult"
    return "Older adult"


def parse_date_value(value: Any) -> date | None:
    text_value = clean_text(value)
    if text_value is None:
        return None

    try:
        return date.fromisoformat(text_value)
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


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
