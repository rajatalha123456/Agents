import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class AuditLog(Base):
    """Append-only log: who asked, what was retrieved, what was answered, review action. FR-19."""

    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False)
    query_text = Column(Text, nullable=False)
    retrieved_document_ids = Column(Text, nullable=True)   # JSON-encoded list
    ai_answer_summary = Column(Text, nullable=True)
    evidence_pack_id = Column(String, nullable=True)
    reviewer_action = Column(String, nullable=True)  # null | "approved" | "rejected"
    created_at = Column(DateTime, default=datetime.utcnow)
