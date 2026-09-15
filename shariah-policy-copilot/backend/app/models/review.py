import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, Enum

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class ReviewStatus(str, enum.Enum):
    HUMAN_REVIEW_REQUIRED = "human_review_required"  # default, always (FR-17)
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidencePack(Base):
    """The full structured output package. FR-13, FR-16, FR-17, FR-18."""

    __tablename__ = "evidence_packs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False)
    question = Column(Text, nullable=False)

    relevant_rulings = Column(Text, nullable=True)      # JSON
    relevant_standards = Column(Text, nullable=True)    # JSON
    key_evidence_excerpts = Column(Text, nullable=True)  # JSON
    comparison_table = Column(Text, nullable=True)       # JSON
    open_issues = Column(Text, nullable=True)            # JSON list of strings
    citations = Column(Text, nullable=True)              # JSON
    research_summary = Column(Text, nullable=False)
    conflict_flagged = Column(String, nullable=False, default="no")  # "yes"/"no" — kept simple/queryable
    disclaimer = Column(Text, nullable=False)

    review_status = Column(Enum(ReviewStatus), nullable=False, default=ReviewStatus.HUMAN_REVIEW_REQUIRED)
    reviewer_id = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
