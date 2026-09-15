from __future__ import annotations

from sqlalchemy import ARRAY, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPk


class Tenant(Base, UUIDPk, TimestampMixin):
    """§4.2 — organization. `active_packs` lists installed pack ids+versions."""

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="UTC")
    close_calendar_id: Mapped[str | None] = mapped_column(String, nullable=True)
    active_packs: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
