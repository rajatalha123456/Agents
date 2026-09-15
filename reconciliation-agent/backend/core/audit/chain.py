"""
§4.4 / §23 — tamper-evident audit chain.

Every audit_event carries the hash of the previous event for its tenant.
The DB enforces insert-only (trigger installed in migrations); this module
enforces the *hash* half of the guarantee: you cannot construct a valid
AuditEvent without correctly chaining to whatever came before it, and
`verify_chain` can detect a gap or a tampered row after the fact.

Deliberately dependency-free (stdlib only) so it can be unit tested without
a database.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def compute_event_hash(
    *,
    tenant_id: str,
    actor: str,
    event_type: str,
    before: dict | None,
    after: dict | None,
    correlation_id: str | None,
    created_at: datetime,
    hash_prev: str | None,
) -> str:
    """
    Deterministic hash over the event's own content plus the previous
    event's hash. Changing any field, or splicing a different
    predecessor, changes this value — that's what makes the chain
    tamper-evident.
    """
    payload = _canonical_json(
        {
            "tenant_id": str(tenant_id),
            "actor": actor,
            "event_type": event_type,
            "before": before,
            "after": after,
            "correlation_id": correlation_id,
            "created_at": created_at.isoformat(),
            "hash_prev": hash_prev,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainableEvent:
    """A minimal, DB-agnostic view of an audit_event row, for chain verification."""

    tenant_id: str
    actor: str
    event_type: str
    before: dict | None
    after: dict | None
    correlation_id: str | None
    created_at: datetime
    hash_prev: str | None
    hash_self: str


def verify_chain(events: list[ChainableEvent]) -> list[str]:
    """
    Verify a tenant's audit events in insertion order. Returns a list of
    human-readable problems; an empty list means the chain is intact.
    """
    problems: list[str] = []
    prev_hash: str | None = None
    for i, event in enumerate(events):
        expected = compute_event_hash(
            tenant_id=event.tenant_id,
            actor=event.actor,
            event_type=event.event_type,
            before=event.before,
            after=event.after,
            correlation_id=event.correlation_id,
            created_at=event.created_at,
            hash_prev=event.hash_prev,
        )
        if event.hash_prev != prev_hash:
            problems.append(f"event[{i}]: hash_prev does not match preceding event's hash_self")
        if event.hash_self != expected:
            problems.append(f"event[{i}]: hash_self does not match recomputed hash (tampered?)")
        prev_hash = event.hash_self
    return problems
