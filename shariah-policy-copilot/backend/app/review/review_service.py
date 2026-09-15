from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.audit_service import log_review_action
from app.models.review import EvidencePack, ReviewStatus


def set_review_status(db: Session, evidence_pack_id: str, reviewer_id: str, approve: bool) -> EvidencePack:
    pack = db.query(EvidencePack).get(evidence_pack_id)
    if pack is None:
        raise ValueError(f"Evidence pack not found: {evidence_pack_id}")

    pack.review_status = ReviewStatus.APPROVED if approve else ReviewStatus.REJECTED
    pack.reviewer_id = reviewer_id
    pack.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(pack)

    log_review_action(db, evidence_pack_id, reviewer_id, "approved" if approve else "rejected")
    return pack
