"""The shared Blackboard: the ONLY way agents communicate in this system.

Why it exists: in a blackboard architecture, agents never call each other directly.
Each agent reads the signals it needs from this shared object and writes (posts)
its own findings back to it. The CoordinatorAgent then decides ONLY from what is
posted here, so every decision can be traced back to concrete, attributed evidence.

Every posting is typed (a `status` of ok / missing / error), records which agent
wrote it (`author`) and when (`timestamp`), and is kept in an append-only history.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Allowed statuses for a posting. "missing" and "error" are first-class signals:
# an agent that could not find data says so explicitly instead of staying silent.
VALID_STATUSES = ("ok", "missing", "error")


@dataclass
class Posting:
    """One entry on the blackboard."""
    key: str                  # e.g. "inventory:ITM-001@WH-DEL"
    value: Any                # the payload (dict / list / str)
    author: str               # agent name that posted it
    status: str = "ok"        # ok | missing | error
    note: str = ""            # short human-readable explanation
    tools: list[str] = field(default_factory=list)  # tools used to produce it
    timestamp: str = ""       # ISO-8601 UTC, filled in by Blackboard.post

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Blackboard:
    """A small, thread-safe key/value store of attributed postings."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._latest: dict[str, Posting] = {}   # current value per key
        self._history: list[Posting] = []       # every posting ever made, in order
        self._lock = threading.Lock()

    # ---------- write API ----------
    def post(self, key: str, value: Any, author: str, status: str = "ok",
             note: str = "", tools: list[str] | None = None) -> Posting:
        """Write (or overwrite) a signal. The old value stays in history."""
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
        posting = Posting(key=key, value=value, author=author, status=status, note=note,
                          tools=list(tools or []),
                          timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
        with self._lock:
            self._latest[key] = posting
            self._history.append(posting)
        return posting

    # ---------- read API ----------
    def get(self, key: str) -> Posting | None:
        """Return the latest posting for a key, or None if nobody posted it."""
        with self._lock:
            return self._latest.get(key)

    def read(self, key: str, default: Any = None) -> Any:
        """Return just the value of an OK posting (None/default if missing or not ok)."""
        posting = self.get(key)
        if posting is None or posting.status != "ok":
            return default
        return posting.value

    def has_ok(self, key: str) -> bool:
        """True only if the key exists AND its status is ok."""
        posting = self.get(key)
        return posting is not None and posting.status == "ok"

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return [k for k in self._latest if k.startswith(prefix)]

    def snapshot(self) -> list[dict[str, Any]]:
        """The full current state, in the order keys were first posted."""
        with self._lock:
            return [p.to_dict() for p in self._latest.values()]

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in self._history]

    def render(self) -> str:
        """A readable table of the current blackboard state for the trace."""
        lines = [f"BLACKBOARD (run {self.run_id}) - {len(self._latest)} entries"]
        for p in self._latest.values():
            time_part = p.timestamp[11:23]
            lines.append(f"  [{time_part}] {p.author:<16} {p.status:<7} {p.key:<34} {_short(p.value)}")
        return "\n".join(lines)


def _short(value: Any, limit: int = 90) -> str:
    """Compact one-line preview of a value."""
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
