from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class AuditEvent(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.4 / §23 — immutable, hash-chained audit log. INSERT only: the
    migration that creates this table also installs a trigger that raises
    on UPDATE/DELETE, so "insert-only" is a database guarantee, not an
    application-layer promise. See core/audit/chain.py for hash computation
    and tests/security for the guardrail that verifies the trigger exists.
    """

    __tablename__ = "audit_event"

    actor: Mapped[str] = mapped_column(String, nullable=False)  # human actor id or "AGENT"
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    hash_prev: Mapped[str | None] = mapped_column(String, nullable=True)
    hash_self: Mapped[str] = mapped_column(String, nullable=False)
