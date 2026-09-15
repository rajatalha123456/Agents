from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.review.review_service import set_review_status
from app.utils.security import CurrentUser, get_current_user, require_reviewer

router = APIRouter(prefix="/review", tags=["review"])


class ReviewDecision(BaseModel):
    approve: bool


@router.post("/{evidence_pack_id}")
def review_evidence_pack(
    evidence_pack_id: str,
    decision: ReviewDecision,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """FR-18: only a Shariah reviewer may mark a pack Reviewed/Approved (or reject it)."""
    require_reviewer(user)
    pack = set_review_status(db, evidence_pack_id, reviewer_id=user.user_id, approve=decision.approve)
    return {
        "id": pack.id,
        "review_status": pack.review_status.value,
        "reviewer_id": pack.reviewer_id,
        "reviewed_at": str(pack.reviewed_at),
    }
