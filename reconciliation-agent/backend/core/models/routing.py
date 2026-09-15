from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class RoutingRule(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    EP-04 — (break_family, amount_band, dimension_filter) -> required_role.
    Packs supply rows here (e.g. a domain pack's sensitive break family
    routed to a specialist review role with allow_auto_match=false, §5.3)
    — core only runs the routing engine, it never hardcodes a role name
    or a family.

    `allow_auto_match = false` always wins over any other matching rule,
    checked explicitly in the routing engine (§5.3) — restriction beats
    permission, unconditionally.
    """

    __tablename__ = "routing_rule"

    break_family: Mapped[str] = mapped_column(String, nullable=False)
    amount_band: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"gte": 1000000}
    dimension_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    required_role: Mapped[str] = mapped_column(String, nullable=False)
    escalation_role: Mapped[str | None] = mapped_column(String, nullable=True)
    allow_auto_match: Mapped[bool] = mapped_column(default=True)
    pack_id: Mapped[str] = mapped_column(String, nullable=False)
