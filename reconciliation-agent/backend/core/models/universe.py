from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class AutonomyLevel(str, enum.Enum):
    """§1.2 — configured per universe, per tenant. A4 deliberately does not exist."""

    A0_OBSERVE = "A0"
    A1_PROPOSE_ON_DEMAND = "A1"
    A2_PROPOSE_ON_SCHEDULE = "A2"
    A3_AUTO_MATCH = "A3"


class Universe(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 / EP-08 — a reconciliation definition, stored as data so new
    universes need no deploy. `code` is unique per tenant.
    """

    __tablename__ = "universe"

    code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    side_a_filter: Mapped[dict] = mapped_column(JSONB, default=dict)
    side_b_filter: Mapped[dict] = mapped_column(JSONB, default=dict)
    match_keys: Mapped[list] = mapped_column(JSONB, default=list)
    tolerance_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tolerance_profile.id"), nullable=True
    )
    require_dimension: Mapped[list] = mapped_column(JSONB, default=list)
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        Enum(AutonomyLevel, name="autonomy_level"), default=AutonomyLevel.A2_PROPOSE_ON_SCHEDULE
    )


class ReconRun(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 — one execution. `pack_versions` pins reproducibility (NFR-07)."""

    __tablename__ = "recon_run"

    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universe.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    pack_versions: Mapped[dict] = mapped_column(JSONB, default=dict)
