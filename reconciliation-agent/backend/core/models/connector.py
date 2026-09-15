from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class Connector(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 / §6 — a single read-only data source. `credentials_ref` points
    into a secrets vault; credentials never live in this table (§6.3).
    """

    __tablename__ = "connector"

    type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. BANK_STATEMENT, SUBLEDGER
    format: Mapped[str] = mapped_column(String, nullable=False)  # CSV, MT940, CAMT053, ...
    schedule: Mapped[str | None] = mapped_column(String, nullable=True)  # cron expression
    credentials_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    mapping_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mapping_template.id"), nullable=True
    )
    read_only_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MappingTemplate(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 / §17.1 — column mapping config, keyed by header-hash signature."""

    __tablename__ = "mapping_template"

    source_signature: Mapped[str] = mapped_column(String, nullable=False, index=True)
    field_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transforms: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ImportBatch(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 / §6.2 — one file/pull. `idempotency_key` prevents duplicate
    ingestion of the same file; a partial import is never committed
    (all-or-nothing per §6.2).
    """

    __tablename__ = "import_batch"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connector.id"), nullable=False
    )
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    row_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    control_totals: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING")  # PENDING/COMMITTED/HELD/REJECTED
