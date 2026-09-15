from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class BreakCaseStatus(str, enum.Enum):
    """
    §4.3 — case lifecycle, kept separate from record lifecycle (v2's mistake).

    OPEN -> TRIAGED -> PROPOSED -> UNDER_REVIEW -> {APPROVED, REJECTED, RETURNED}
    REJECTED/RETURNED -> TRIAGED
    APPROVED -> ACTION_PENDING -> RESOLVED -> CLOSED
    CLOSED -> REOPENED -> TRIAGED   (separate permission + mandatory reason)

    CARRIED_FORWARD is a distinct terminal-of-period state (§16), not part
    of the linear flow above — a period close can push any OPEN-ish case
    into it without otherwise changing its state.
    """

    OPEN = "OPEN"
    TRIAGED = "TRIAGED"
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"
    ACTION_PENDING = "ACTION_PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    CARRIED_FORWARD = "CARRIED_FORWARD"


class BreakCase(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 — an unresolved reconciliation item."""

    __tablename__ = "break_case"

    break_type_code: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[str | None] = mapped_column(Numeric(28, 8), nullable=True)
    age_days: Mapped[int] = mapped_column(Integer, default=0)
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[BreakCaseStatus] = mapped_column(
        Enum(BreakCaseStatus, name="break_case_status"), default=BreakCaseStatus.OPEN
    )
    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universe.id"), nullable=False
    )
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)

    # §16 roll-forward bookkeeping
    carry_forward_count: Mapped[int] = mapped_column(Integer, default=0)
    original_period: Mapped[str | None] = mapped_column(String, nullable=True)
