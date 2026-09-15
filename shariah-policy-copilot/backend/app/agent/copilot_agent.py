import json

from sqlalchemy.orm import Session

from app.agent import llm_client
from app.agent.conflict_detector import verify_conflict_flag
from app.agent.evidence_pack_builder import build_and_persist
from app.agent.prompts import build_user_prompt
from app.audit.audit_service import log_query
from app.config import DISCLAIMER_TEXT, NO_EVIDENCE_FALLBACK
from app.retrieval.hybrid_retriever import retrieve
from app.schemas.evidence_pack import EvidencePackOut
from app.schemas.query import QueryFilters


def ask(db: Session, user_id: str, question: str, filters: QueryFilters) -> EvidencePackOut:
    retrieved = retrieve(db, question, filters)

    # FR-15: no approved evidence -> fixed fallback, never fall back to general knowledge
    if not retrieved:
        pack = EvidencePackOut(
            id="",
            question=question,
            research_summary=NO_EVIDENCE_FALLBACK,
            relevant_rulings=[],
            relevant_standards=[],
            key_evidence_excerpts=[],
            comparison_table=[],
            open_issues=["No matching approved evidence was found for this query."],
            citations=[],
            conflict_flagged=False,
            disclaimer=DISCLAIMER_TEXT,
            review_status="human_review_required",
            is_fallback=True,
        )
        log_query(db, user_id=user_id, question=question, retrieved_document_ids=[], answer_summary=pack.research_summary)
        return pack

    evidence_blocks = [
        f"[document_id={rc.document.id}] {rc.document.document_name} "
        f"(v{rc.document.version}, {rc.document.approval_status.value}, "
        f"section={rc.chunk.section_label or 'n/a'}, page={rc.chunk.page_number or 'n/a'}):\n"
        f"{rc.chunk.text}"
        for rc in retrieved
    ]

    user_prompt = build_user_prompt(question, evidence_blocks)
    raw_response = llm_client.generate(user_prompt)
    llm_output = _parse_llm_json(raw_response)

    # FR-10: still enforce grounding even if the model tries to answer with no real match
    if llm_output.get("research_summary") == "NO_EVIDENCE_FOUND":
        pack = EvidencePackOut(
            id="",
            question=question,
            research_summary=NO_EVIDENCE_FALLBACK,
            relevant_rulings=[], relevant_standards=[], key_evidence_excerpts=[],
            comparison_table=[], open_issues=["Retrieved evidence did not directly address the question."],
            citations=[], conflict_flagged=False, disclaimer=DISCLAIMER_TEXT,
            review_status="human_review_required", is_fallback=True,
        )
        log_query(db, user_id=user_id, question=question,
                  retrieved_document_ids=[rc.document.id for rc in retrieved],
                  answer_summary=pack.research_summary)
        return pack

    distinct_doc_ids = [rc.document.id for rc in retrieved]
    llm_output = verify_conflict_flag(llm_output, distinct_doc_ids)  # FR-14 backstop

    pack = build_and_persist(db, user_id, question, retrieved, llm_output)

    log_query(
        db, user_id=user_id, question=question,
        retrieved_document_ids=distinct_doc_ids,
        answer_summary=pack.research_summary,
        evidence_pack_id=pack.id,
    )
    return pack


def _parse_llm_json(raw: str) -> dict:
    """LLMs sometimes wrap JSON in prose or code fences despite instructions — strip defensively."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        # Model didn't return parseable JSON at all — treat as no answer rather than guess.
        return {"research_summary": "NO_EVIDENCE_FOUND"}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"research_summary": "NO_EVIDENCE_FOUND"}
