"""PostgreSQL-backed audit trail: same interface as sampling.audit_trail's
JSONL AuditTrail, same hash chain, serialized per tenant via an advisory
lock so concurrent appends cannot fork the chain.

Reuses _compute_hash from sampling.audit_trail unchanged so a JSONL trail
and a Postgres trail verify identically -- the hash material must never
diverge between the two storages.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_trail import GENESIS_HASH, AuditEvent, TamperReport, _compute_hash
from .models import AuditEventRow


class PgAuditTrail:
    """Serializes appends per tenant with pg_advisory_xact_lock so two
    concurrent writers cannot both read the same head and produce a
    forked, unverifiable chain. The lock is transaction-scoped and
    releases automatically on commit or rollback.
    """

    def __init__(self, tenant_id: uuid.UUID | str):
        self.tenant_id = str(tenant_id)

    async def _head(self, session: AsyncSession) -> AuditEventRow | None:
        result = await session.execute(
            select(AuditEventRow)
            .where(AuditEventRow.tenant_id == self.tenant_id)
            .order_by(AuditEventRow.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def head(self, session: AsyncSession) -> AuditEvent | None:
        row = await self._head(session)
        return _row_to_event(row) if row else None

    async def head_hash(self, session: AsyncSession) -> str:
        row = await self._head(session)
        return row.event_hash if row else GENESIS_HASH

    async def events(self, session: AsyncSession) -> list[AuditEvent]:
        result = await session.execute(
            select(AuditEventRow)
            .where(AuditEventRow.tenant_id == self.tenant_id)
            .order_by(AuditEventRow.sequence.asc())
        )
        return [_row_to_event(r) for r in result.scalars()]

    async def for_subject(self, session: AsyncSession, subject: str) -> list[AuditEvent]:
        result = await session.execute(
            select(AuditEventRow)
            .where(AuditEventRow.tenant_id == self.tenant_id, AuditEventRow.subject == subject)
            .order_by(AuditEventRow.sequence.asc())
        )
        return [_row_to_event(r) for r in result.scalars()]

    async def append(
        self, session: AsyncSession, actor: str, action: str, subject: str, payload: dict
    ) -> AuditEvent:
        # Per-tenant advisory lock: concurrent appends would otherwise both
        # read the same head hash and produce a forked, unverifiable chain.
        # hashtext() collapses the tenant UUID string to a 32-bit lock key;
        # a hash collision between two tenants only costs extra
        # serialization, never incorrect isolation, since the chain itself
        # is still filtered and validated per tenant_id.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:tid))"),
            {"tid": self.tenant_id},
        )

        head_row = await self._head(session)
        sequence = (head_row.sequence + 1) if head_row else 0
        previous_hash = head_row.event_hash if head_row else GENESIS_HASH
        timestamp = datetime.now(UTC)

        event_hash = _compute_hash(
            sequence, timestamp.isoformat(), self.tenant_id, actor, action, subject,
            payload, previous_hash,
        )

        row = AuditEventRow(
            tenant_id=self.tenant_id,
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        session.add(row)
        await session.flush()
        return _row_to_event(row)

    async def verify(self, session: AsyncSession) -> TamperReport:
        events = await self.events(session)
        expected_previous = GENESIS_HASH
        for i, e in enumerate(events):
            if e.sequence != i:
                return TamperReport(valid=False, first_invalid_sequence=i, reason="sequence gap", events_checked=i)
            if e.previous_hash != expected_previous:
                return TamperReport(
                    valid=False, first_invalid_sequence=e.sequence,
                    reason="chain break: previous_hash mismatch", events_checked=i,
                )
            recomputed = _compute_hash(
                e.sequence, e.timestamp, e.tenant_id, e.actor, e.action, e.subject,
                e.payload, e.previous_hash,
            )
            if recomputed != e.event_hash:
                return TamperReport(
                    valid=False, first_invalid_sequence=e.sequence,
                    reason="content altered", events_checked=i,
                )
            expected_previous = e.event_hash
        return TamperReport(valid=True, events_checked=len(events))


def _row_to_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        sequence=row.sequence,
        timestamp=row.timestamp.isoformat() if isinstance(row.timestamp, datetime) else row.timestamp,
        tenant_id=str(row.tenant_id),
        actor=row.actor,
        action=row.action,
        subject=row.subject,
        payload=row.payload,
        previous_hash=row.previous_hash,
        event_hash=row.event_hash,
    )
