import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class ApprovalStatus(str, enum.Enum):
    APPROVED = "approved"          # 🟢
    UNDER_REVIEW = "under_review"  # 🟡
    DRAFT = "draft"                # 🔴
    ARCHIVED = "archived"          # ⚫


class Document(Base):
    """A source Shariah document (ruling, standard, policy, circular, etc.). FR-1/FR-2/FR-3."""

    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    document_name = Column(String, nullable=False)
    document_type = Column(String, nullable=False)  # ruling|fatwa|standard|policy|resolution|minutes|circular|sop|guideline
    version = Column(String, nullable=False, default="1.0")
    approval_status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.DRAFT)
    approval_date = Column(DateTime, nullable=True)
    effective_date = Column(DateTime, nullable=True)
    expiry_review_date = Column(DateTime, nullable=True)
    product_category = Column(String, nullable=True)
    jurisdiction = Column(String, nullable=True)
    approved_by = Column(String, nullable=True)
    confidentiality_level = Column(String, nullable=False, default="internal")

    source_file_path = Column(String, nullable=True)
    is_current_version = Column(Integer, nullable=False, default=1)  # 1=current, 0=superseded (NFR-4)
    supersedes_document_id = Column(String, ForeignKey("documents.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    @property
    def status_emoji(self) -> str:
        return {
            ApprovalStatus.APPROVED: "🟢",
            ApprovalStatus.UNDER_REVIEW: "🟡",
            ApprovalStatus.DRAFT: "🔴",
            ApprovalStatus.ARCHIVED: "⚫",
        }[self.approval_status]


class DocumentChunk(Base):
    """A section/clause-level chunk. Carries parent metadata for citation (FR-4, FR-11)."""

    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_label = Column(String, nullable=True)   # e.g. "Clause 4.2"
    page_number = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)

    document = relationship("Document", back_populates="chunks")
