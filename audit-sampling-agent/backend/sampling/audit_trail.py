"""Single-writer, hash-chained JSONL audit trail.

Does not prevent tampering -- makes it detectable. The hash material stays
stable so Phase 1's PostgreSQL implementation can reuse _compute_hash
unchanged and both storages verify identically.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    tenant_id: str
    actor: str
    action: str
    subject: str
    payload: dict
    previous_hash: str
    event_hash: str

    def as_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "action": self.action,
            "subject": self.subject,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


@dataclass(frozen=True)
class TamperReport:
    valid: bool
    first_invalid_sequence: int | None = None
    reason: str | None = None
    events_checked: int = 0


def _compute_hash(
    sequence: int,
    timestamp: str,
    tenant_id: str,
    actor: str,
    action: str,
    subject: str,
    payload: dict,
    previous_hash: str,
) -> str:
    material = json.dumps(
        {
            "sequence": sequence,
            "timestamp": timestamp,
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "subject": subject,
            "payload": payload,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AuditTrail:
    """Single-writer JSONL-backed hash chain, one file per tenant."""

    def __init__(self, path: str, tenant_id: str):
        self.path = path
        self.tenant_id = tenant_id
        self._lock = threading.Lock()
        if not os.path.exists(path):
            open(path, "a", encoding="utf-8").close()

    def _read_all(self) -> list[AuditEvent]:
        events = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                events.append(AuditEvent(**d))
        return events

    def events(self) -> list[AuditEvent]:
        return self._read_all()

    def head(self) -> AuditEvent | None:
        events = self._read_all()
        return events[-1] if events else None

    def head_hash(self) -> str:
        head = self.head()
        return head.event_hash if head else GENESIS_HASH

    def for_subject(self, subject: str) -> list[AuditEvent]:
        return [e for e in self._read_all() if e.subject == subject]

    def append(self, actor: str, action: str, subject: str, payload: dict) -> AuditEvent:
        with self._lock:
            head = self.head()
            sequence = (head.sequence + 1) if head else 0
            previous_hash = head.event_hash if head else GENESIS_HASH
            timestamp = datetime.now(UTC).isoformat()

            event_hash = _compute_hash(
                sequence, timestamp, self.tenant_id, actor, action, subject,
                payload, previous_hash,
            )
            event = AuditEvent(
                sequence=sequence,
                timestamp=timestamp,
                tenant_id=self.tenant_id,
                actor=actor,
                action=action,
                subject=subject,
                payload=payload,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.as_dict(), separators=(",", ":")) + "\n")
            return event

    def verify(self) -> TamperReport:
        events = self._read_all()
        expected_previous = GENESIS_HASH
        for i, e in enumerate(events):
            if e.sequence != i:
                return TamperReport(
                    valid=False, first_invalid_sequence=i,
                    reason="sequence gap", events_checked=i,
                )
            if e.previous_hash != expected_previous:
                return TamperReport(
                    valid=False, first_invalid_sequence=e.sequence,
                    reason="chain break: previous_hash mismatch",
                    events_checked=i,
                )
            recomputed = _compute_hash(
                e.sequence, e.timestamp, e.tenant_id, e.actor, e.action,
                e.subject, e.payload, e.previous_hash,
            )
            if recomputed != e.event_hash:
                return TamperReport(
                    valid=False, first_invalid_sequence=e.sequence,
                    reason="content altered", events_checked=i,
                )
            expected_previous = e.event_hash
        return TamperReport(valid=True, events_checked=len(events))
