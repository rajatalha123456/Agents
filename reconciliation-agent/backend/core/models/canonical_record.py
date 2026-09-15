from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class RecordSide(str, enum.Enum):
    SOURCE_A = "SOURCE_A"
    SOURCE_B = "SOURCE_B"


class Direction(str, enum.Enum):
    DR = "DR"
    CR = "CR"


class RecordStatus(str, enum.Enum):
    """§4.3 — record lifecycle, deliberately separate from break_case lifecycle."""

    INGESTED = "INGESTED"
    NORMALIZED = "NORMALIZED"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    QUARANTINED = "QUARANTINED"


class CanonicalRecord(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.1 — the pack-neutral canonical record. Every domain-specific fact
    lives in `dimensions` (EP-01), never as a new column here.

    Money is always `Numeric`, never float/double (§4.4). `raw_payload`
    is immutable after posting — enforced by a DB trigger in migrations,
    not by convention.
    """

    __tablename__ = "canonical_record"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    side: Mapped[RecordSide] = mapped_column(Enum(RecordSide, name="record_side"), nullable=False)
    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connector.id"), nullable=False
    )

    external_ref: Mapped[str] = mapped_column(String, nullable=False)
    posted_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    booking_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    amount: Mapped[str] = mapped_column(Numeric(28, 8), nullable=False)
    direction: Mapped[Direction] = mapped_column(Enum(Direction, name="direction"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[str | None] = mapped_column(Numeric(28, 12), nullable=True)
    base_amount: Mapped[str] = mapped_column(Numeric(28, 8), nullable=False)

    account_ref: Mapped[str] = mapped_column(String, nullable=False)
    counterparty_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    reference_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    reference_canonical: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    description_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    description_clean: Mapped[str | None] = mapped_column(String, nullable=True)

    # EP-01: pack's extension surface. GIN-indexed in migrations.
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Original, never mutated after posting (enforced by DB trigger).
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    row_fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)

    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status"), default=RecordStatus.INGESTED
    )
    quarantine_reason: Mapped[str | None] = mapped_column(String, nullable=True)
