from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class AgentRun(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 / §11 — one agent execution. `budget_used` records what §11.4
    caps were consumed, so an operator can see exactly why cases were
    left NOT_ANALYSED.
    """

    __tablename__ = "agent_run"

    autonomy_level: Mapped[str] = mapped_column(String, nullable=False)
    budget_used: Mapped[dict] = mapped_column(JSONB, default=dict)
    cases_analysed: Mapped[int] = mapped_column(default=0)
    cases_skipped: Mapped[dict] = mapped_column(JSONB, default=dict)  # {case_id: reason}
    outcome: Mapped[str] = mapped_column(String, default="RUNNING")
