"""Activity log for admin inspection.

Stores timestamped entries for all significant actions:
placements, moves, deletions, mesh uploads, etc.
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional


class ActivityLog:
    """Append-only JSON-lines activity log."""

    def __init__(self, data_file: str):
        self._data_file = data_file
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        if not os.path.exists(data_file):
            self._write([])

    def log(self, action: str, user: str = "", details: Optional[dict] = None):
        """Append one log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "user": user,
            "details": details or {},
        }
        entries = self._read()
        entries.append(entry)
        self._write(entries)

    def list(self, limit: int = 200, action: Optional[str] = None) -> List[dict]:
        """Return the most recent entries (newest first)."""
        entries = self._read()
        if action:
            entries = [e for e in entries if e.get("action") == action]
        return list(reversed(entries[-limit:]))

    def _read(self) -> list:
        with open(self._data_file, "r") as fh:
            return json.load(fh)

    def _write(self, data: list):
        with open(self._data_file, "w") as fh:
            json.dump(data, fh, indent=2)
