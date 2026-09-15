from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class ClosePeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    SOFT_CLOSE = "SOFT_CLOSE"
    HARD_CLOSE = "HARD_CLOSE"
    CERTIFIED = "CERTIFIED"
    LOCKED = "LOCKED"


class ClosePeriod(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§15.1 — the close calendar. `certify` is a human/system action; the agent has no such tool (§12.3)."""

    __tablename__ = "close_period"

    period: Mapped[str] = mapped_column(String, nullable=False)  # "2026-09"
    status: Mapped[ClosePeriodStatus] = mapped_column(
        Enum(ClosePeriodStatus, name="close_period_status"), default=ClosePeriodStatus.OPEN
    )
    deadline_prep: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_review: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_certify: Mapped[date | None] = mapped_column(Date, nullable=True)
    certifier: Mapped[str | None] = mapped_column(String, nullable=True)
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountReconciliation(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §15.2 — account-level close item. `unexplained` is the actual
    reconciliation output that auditors care about.
    """

    __tablename__ = "account_reconciliation"

    account_ref: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)
    opening_balance: Mapped[str] = mapped_column(Numeric(28, 8), nullable=False)
    movement: Mapped[str] = mapped_column(Numeric(28, 8), nullable=False)
    closing_balance: Mapped[str] = mapped_column(Numeric(28, 8), nullable=False)
    explained: Mapped[str] = mapped_column(Numeric(28, 8), default=0)
    unexplained: Mapped[str] = mapped_column(Numeric(28, 8), default=0)
    supporting_evidence: Mapped[list] = mapped_column(JSONB, default=list)
    preparer: Mapped[str | None] = mapped_column(String, nullable=True)
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_rating: Mapped[str] = mapped_column(String, default="LOW")
