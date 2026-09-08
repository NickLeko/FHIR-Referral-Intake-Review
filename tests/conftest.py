from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import load_json_file


@pytest.fixture
def sample_bundle_dir() -> Path:
    return Path("data/sample_bundles")


@pytest.fixture
def load_sample_bundle():
    def _load(path: Path) -> dict:
        return load_json_file(path)

    return _load


@pytest.fixture(autouse=True)
def isolate_fhir_environment(monkeypatch):
    """Tests stay offline even in a shell that sourced real sandbox credentials."""
    for name in (
        "FHIR_AUTH_MODE",
        "FHIR_BASE_URL",
        "FHIR_TOKEN_URL",
        "FHIR_CLIENT_ID",
        "FHIR_PRIVATE_KEY_PEM",
        "FHIR_KEY_ID",
        "FHIR_SCOPES",
    ):
        monkeypatch.delenv(name, raising=False)
