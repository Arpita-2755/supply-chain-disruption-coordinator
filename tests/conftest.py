"""Pytest setup: make the project importable, force offline mode, and send the
run log of each test to a temporary file so tests never touch the real log."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def offline_and_temp_log(monkeypatch, tmp_path):
    for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SCC_MODE", "auto")          # auto + no keys => offline
    log_file = tmp_path / "run_log.jsonl"
    monkeypatch.setenv("SCC_RUN_LOG", str(log_file))
    yield log_file
