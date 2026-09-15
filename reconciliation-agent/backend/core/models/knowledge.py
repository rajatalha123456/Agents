from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk

try:
    from pgvector.sqlalchemy import Vector  # type: ignore
except ImportError:  # pragma: no cover - optional dep, see §31 decision on vector store
    Vector = None


class SourceAuthority(str, enum.Enum):
    """§13.3 / §19.3 — hard authority ordering: POLICY > SOP > GUIDANCE > PRECEDENT."""

    POLICY = "POLICY"
    SOP = "SOP"
    GUIDANCE = "GUIDANCE"
    PRECEDENT = "PRECEDENT"


class KnowledgeDocument(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 / EP-06 — RAG source, namespaced per pack so e.g. Islamic finance policy stays separate."""

    __tablename__ = "knowledge_document"

    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # pack-defined document type, e.g. SOP/POLICY/PRECEDENT
    version: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    pack_id: Mapped[str] = mapped_column(String, nullable=False)
    access_level: Mapped[str] = mapped_column(String, default="STANDARD")


class DocumentChunk(Base, UUIDPk, TenantScoped):
    """
    §19.2 — a retrievable unit. Vector store is never a source of financial
    fact (§19.1 / BR-001) — it only ever answers "what does policy say",
    never "what is the balance".
    """

    __tablename__ = "document_chunk"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_document.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_authority: Mapped[SourceAuthority] = mapped_column(
        Enum(SourceAuthority, name="source_authority"), nullable=False
    )
    embedding_model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    if Vector is not None:
        embedding = mapped_column(Vector(1536), nullable=True)


class RetrievalTrace(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§19.4 — every retrieval, so citation validation can check "was this chunk actually returned?"."""

    __tablename__ = "retrieval_trace"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    query: Mapped[str] = mapped_column(String, nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    returned_ids: Mapped[list] = mapped_column(JSONB, default=list)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
