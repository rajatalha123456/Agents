from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class ExternalActionRef(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §14.2 — record of an action a human took in an external ERP/GL. A case
    cannot close (§29.1) without a valid reference + evidence recorded here.
    """

    __tablename__ = "external_action_ref"

    break_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("break_case.id"), nullable=False, index=True
    )
    system: Mapped[str] = mapped_column(String, nullable=False)
    reference_id: Mapped[str] = mapped_column(String, nullable=False)
    performed_by: Mapped[str] = mapped_column(String, nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String, nullable=True)
