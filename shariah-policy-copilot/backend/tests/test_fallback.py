"""AC-3: a query with no matching approved evidence returns the fixed fallback,
never a generated opinion. Uses a fresh in-memory-style SQLite DB per test.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ.setdefault("VECTOR_STORE_DIR", tempfile.mkdtemp())

from app.agent.copilot_agent import ask  # noqa: E402
from app.config import NO_EVIDENCE_FALLBACK  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.schemas.query import QueryFilters  # noqa: E402


def test_no_evidence_returns_fixed_fallback():
    init_db()
    db = SessionLocal()
    try:
        result = ask(db, user_id="test_user", question="Some question with zero matching docs",
                     filters=QueryFilters())
        assert result.is_fallback is True
        assert result.research_summary == NO_EVIDENCE_FALLBACK
        assert result.citations == []
        assert result.conflict_flagged is False
    finally:
        db.close()
