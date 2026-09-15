from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class ToleranceProfile(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 — a named set of field-level tolerance rules (day windows, amount
    absolute/percent bands, ...). Defaults come from the pack (§2.3);
    core only knows the *mechanism* of applying a profile.

    Tolerance changes require maker-checker sign-off (§32) — `approved_by`
    is mandatory before a profile can be referenced by a universe.
    """

    __tablename__ = "tolerance_profile"

    name: Mapped[str] = mapped_column(String, nullable=False)
    rules: Mapped[list] = mapped_column(JSONB, nullable=False)  # [{field, type, value/absolute/percent}, ...]
    priority: Mapped[int] = mapped_column(default=0)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
