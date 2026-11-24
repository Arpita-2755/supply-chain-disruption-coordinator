"""Append-only run log (run_log.jsonl).

Why it exists: the project must keep an auditable record of every agent action
and tool call across ALL runs. The file is only ever opened in append mode ("a"),
so earlier lines can never be rewritten or truncated by this code.

Each line is one JSON object: timestamp, run_id, agent, action, tool, result_summary.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "run_log.jsonl"
_lock = threading.Lock()


def log_path() -> Path:
    """Log location; tests can redirect it with the SCC_RUN_LOG environment variable."""
    return Path(os.environ.get("SCC_RUN_LOG", str(DEFAULT_LOG_PATH)))


def log_event(run_id: str, agent: str, action: str, tool: str = "", result_summary: str = "") -> None:
    """Append exactly one line to the run log. Never truncates (mode "a" only)."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "agent": agent,
        "action": action,
        "tool": tool,
        "result_summary": result_summary[:300],
    }
    with _lock:
        with open(log_path(), "a", encoding="utf-8") as fh:  # APPEND ONLY
            fh.write(json.dumps(record) + "\n")
