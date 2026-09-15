import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.copilot_agent import ask
from app.database import get_db
from app.schemas.evidence_pack import EvidencePackOut
from app.schemas.query import QueryRequest
from app.utils.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/ask", response_model=EvidencePackOut)
def ask_question(
    request: QueryRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """FR-5 to FR-16: natural-language question in, cited Evidence Pack out."""
    try:
        return ask(db, user_id=user.user_id, question=request.question, filters=request.filters)
    except Exception as exc:
        # Raised as HTTPException (not left as a bare 500) so the response still
        # passes through CORSMiddleware — an unhandled exception here bypasses it
        # (Starlette routes bare Exception/500 handlers to ServerErrorMiddleware,
        # which sits outside CORSMiddleware) and the frontend only sees an opaque
        # CORS failure instead of the actual drafting-LLM error.
        logger.exception("Failed to answer question for user %s", user.user_id)
        raise HTTPException(status_code=502, detail=f"Failed to generate an answer: {exc}") from exc
