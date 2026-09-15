from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, UUIDPk


class BreakType(Base, UUIDPk, TenantScoped):
    """
    EP-02 — break type registry as DATA, deliberately not a Python enum.
    The core pack seeds the 48 core codes (§10); any other pack adds its
    own rows (e.g. Mizan's SHA family, §30.2) without touching this table's
    schema or any core code.

    `is_sensitive` (EP-03) is the single flag that keeps a break out of the
    AUTO confidence band no matter how high its calibrated probability is
    (§9.2 override) — core enforces the override, it does not need to know
    *why* a given break type is sensitive.
    """

    __tablename__ = "break_type"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "TIM-01", "SHA-01"
    family: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "TIM", "SHA"
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    pack_id: Mapped[str] = mapped_column(String, nullable=False)
