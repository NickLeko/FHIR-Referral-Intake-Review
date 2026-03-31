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
