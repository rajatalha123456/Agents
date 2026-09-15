"""
Declarative base + shared mixins for the pack-neutral core schema (§4).

Every table that holds tenant data carries `tenant_id` and is protected by a
PostgreSQL Row-Level Security policy (§20) — created in the Alembic
migrations, not enforced in application code, so a forgotten WHERE clause
can never leak across tenants.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDPk:
    """Standard uuid primary key, matches `id uuid, pk` in every §4 table."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TenantScoped:
    """
    `tenant_id` on every table (§20). NOT NULL, indexed, foreign key to
    tenant. The RLS policy that actually enforces isolation lives in the
    migration that creates the table, keyed on this column.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
