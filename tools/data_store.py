"""Tiny helper that loads the JSON files in /data.

Why it exists: every tool reads local sample data; keeping the file access in one
place means the tools stay short and tests can point SCC_DATA_DIR at other data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    return Path(os.environ.get("SCC_DATA_DIR", str(DEFAULT_DATA_DIR)))


def load_json(name: str) -> dict[str, Any]:
    """Load data/<name>.json and return it as a dict."""
    with open(data_dir() / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)
