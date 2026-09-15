from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class DecidedBy(str, enum.Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class MatchGroup(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 / §4.4 — a matched set. Auto-matched groups MUST carry
    decided_by=AGENT and autonomy_level=A3 together (checked in the
    matching engine, not left to chance) — see tests/unit/test_match_group.py.

    Isolating-dimension violations are prevented at the DB layer
    (constraint/trigger in migrations), not only in application code.
    """

    __tablename__ = "match_group"

    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universe.id"), nullable=False
    )
    cardinality: Mapped[str] = mapped_column(String, nullable=False)  # "1:1", "1:N", "N:1", "N:M"
    confidence: Mapped[str] = mapped_column(Numeric(6, 5), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_by: Mapped[DecidedBy] = mapped_column(Enum(DecidedBy, name="decided_by"), nullable=False)
    decided_autonomy_level: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MatchMember(Base, UUIDPk, TenantScoped):
    """§4.2 — a member of a match_group."""

    __tablename__ = "match_member"

    match_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_group.id"), nullable=False, index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_record.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # primary/offset/fee
