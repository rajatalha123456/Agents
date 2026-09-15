"""Append-only audit log. JSONL now; swap for a database later by
reimplementing `append_record` behind the same signature — nothing else
in the app should need to change.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src import config

_write_lock = threading.Lock()


@dataclass
class AuditRecord:
    run_id: str
    language: str
    timestamp: str
    verification_result: dict
    generation_status: str  # "success" | "refused"
    generated_output: str | None
    numbers_used: list[str]
    failure_reason: str | None = None

    @staticmethod
    def now(**kwargs) -> "AuditRecord":
        return AuditRecord(timestamp=datetime.now(timezone.utc).isoformat(), **kwargs)


def append_record(record: AuditRecord, path: str | None = None) -> None:
    """Append one immutable audit record. Never updates or deletes."""
    log_path = Path(path or config.AUDIT_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(record), default=str)
    with _write_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_records(path: str | None = None) -> list[dict]:
    """Read back all audit records. Used by tests/ops tooling only."""
    log_path = Path(path or config.AUDIT_LOG_PATH)
    if not log_path.exists():
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
