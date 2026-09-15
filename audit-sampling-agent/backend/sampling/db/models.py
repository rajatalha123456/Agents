"""SQLAlchemy 2.0 models for the audit sampling agent.

Every tenant-scoped table carries tenant_id as the first column after the
primary key, and has row-level security enabled by the corresponding
Alembic migration (see sampling/db/rls.py for the policy SQL). Amounts are
NUMERIC(20,2), never FLOAT -- converted to float only at the pandas frame
boundary in sampling/db/repositories.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AMOUNT = Numeric(20, 2)


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_residency_region: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    llm_provider: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    llm_enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role in ('viewer','auditor','reviewer','admin')", name="ck_users_role"),
    )


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    performance_materiality: Mapped[float | None] = mapped_column(AMOUNT)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    # Unknown until ingest_dataset() has actually read the file -- nullable
    # until the job completes, unlike Phase 1 where rows were inserted
    # synchronously and both were known upfront.
    file_sha256: Mapped[str | None] = mapped_column(Text)
    dataset_fingerprint: Mapped[str | None] = mapped_column(Text)
    ingestion_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    ingestion_error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    column_count: Mapped[int | None] = mapped_column(Integer)
    item_id_col: Mapped[str | None] = mapped_column(Text)
    amount_col: Mapped[str | None] = mapped_column(Text)
    timestamp_col: Mapped[str | None] = mapped_column(Text)
    entity_col: Mapped[str | None] = mapped_column(Text)
    schema_profile: Mapped[dict | None] = mapped_column(JSONB)
    ingestion_warnings: Mapped[list | None] = mapped_column(JSONB)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "file_sha256", name="uq_datasets_tenant_sha256"),
        CheckConstraint(
            "ingestion_status in ('pending','running','complete','failed')",
            name="ck_datasets_ingestion_status",
        ),
    )


class DatasetRow(Base):
    __tablename__ = "dataset_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = mapped_column(AMOUNT, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    flags: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("tenant_id", "dataset_id", "item_id", name="uq_dataset_rows_tenant_dataset_item"),
        Index("ix_dataset_rows_tenant_dataset_item", "tenant_id", "dataset_id", "item_id"),
    )


class SamplingPolicyRow(Base):
    __tablename__ = "sampling_policies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    tolerable_misstatement: Mapped[float | None] = mapped_column(AMOUNT)
    expected_misstatement: Mapped[float | None] = mapped_column(AMOUNT)
    confidence_level: Mapped[float | None] = mapped_column(Numeric(5, 4))
    min_sample_size: Mapped[int | None] = mapped_column(Integer)
    max_sample_size: Mapped[int | None] = mapped_column(Integer)
    high_risk_threshold: Mapped[float | None] = mapped_column(Numeric(6, 2))
    high_risk_top_n: Mapped[int | None] = mapped_column(Integer)
    random_control_size: Mapped[int | None] = mapped_column(Integer)
    test_negative_balances_100pct: Mapped[bool] = mapped_column(Boolean, server_default="true")
    review_zero_balances: Mapped[bool] = mapped_column(Boolean, server_default="false")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "engagement_id", "policy_version", name="uq_policy_tenant_engagement_version"),
    )


class RulePackRow(Base):
    __tablename__ = "rule_packs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    pack_id: Mapped[str] = mapped_column(Text, nullable=False)
    pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    yaml_source: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "pack_id", "pack_version", name="uq_rule_pack_tenant_id_version"),
    )


class RiskRun(Base):
    __tablename__ = "risk_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sampling_policies.id"), nullable=False)
    rule_pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rule_packs.id"))
    run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    user_seed: Mapped[str | None] = mapped_column(Text)
    as_of: Mapped[date | None] = mapped_column(Date)
    dataset_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    risk_manifest: Mapped[dict | None] = mapped_column(JSONB)
    anomaly_manifest: Mapped[dict | None] = mapped_column(JSONB)
    rules_manifest: Mapped[dict | None] = mapped_column(JSONB)
    sample_manifest: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint(
            "status in ('queued','running','complete','failed','cancelled')", name="ck_risk_runs_status"
        ),
    )


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_runs.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float | None] = mapped_column(AMOUNT)
    risk_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    anomaly_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    rule_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    data_quality_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    rules_fired: Mapped[list | None] = mapped_column(JSONB)
    anomaly_attribution: Mapped[list | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "item_id", name="uq_risk_scores_tenant_run_item"),
        Index("ix_risk_scores_tenant_run_score", "tenant_id", "run_id", "risk_score"),
    )


class SampleItem(Base):
    __tablename__ = "sample_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_runs.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    stratum: Mapped[str] = mapped_column(Text, nullable=False)
    selection_basis: Mapped[str] = mapped_column(Text, nullable=False)
    projectable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    amount: Mapped[float | None] = mapped_column(AMOUNT)
    hits: Mapped[int | None] = mapped_column(Integer)
    inclusion_probability: Mapped[float | None] = mapped_column(Numeric(10, 8))
    audit_value: Mapped[float | None] = mapped_column(AMOUNT)
    tested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tester_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "item_id", name="uq_sample_items_tenant_run_item"),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_runs.id"), nullable=False)
    workpaper: Mapped[dict] = mapped_column(JSONB, nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_runs.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    audit_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(reason) >= 10", name="ck_overrides_reason_min_length"),
    )


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_runs.id"), nullable=False)
    label_source: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence", name="uq_audit_events_tenant_sequence"),
        Index("ix_audit_events_tenant_subject", "tenant_id", "subject"),
    )


class AuditAnchor(Base):
    __tablename__ = "audit_anchors"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    head_sequence: Mapped[int | None] = mapped_column(BigInteger)
    head_hash: Mapped[str | None] = mapped_column(String(64))
    anchored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    external_reference: Mapped[str | None] = mapped_column(Text)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id"))

    __table_args__ = (
        Index("ix_refresh_tokens_family", "family_id"),
        Index("ix_refresh_tokens_tenant_user", "tenant_id", "user_id"),
    )


TENANT_SCOPED_TABLES = (
    "users", "engagements", "datasets", "dataset_rows", "sampling_policies",
    "rule_packs", "risk_runs", "risk_scores", "sample_items", "evaluations",
    "overrides", "benchmarks", "audit_events", "audit_anchors", "refresh_tokens",
)
