import json
from typing import Dict, List

from sqlalchemy.orm import Session

from app.config import DISCLAIMER_TEXT
from app.models.review import EvidencePack, ReviewStatus
from app.retrieval.hybrid_retriever import RetrievedChunk
from app.schemas.evidence_pack import Citation, ComparisonRow, EvidenceExcerpt, EvidencePackOut


def build_citation(rc: RetrievedChunk) -> Citation:
    return Citation(
        document_id=rc.document.id,
        document_name=rc.document.document_name,
        version=rc.document.version,
        section_label=rc.chunk.section_label,
        page_number=rc.chunk.page_number,
        approval_date=str(rc.document.approval_date) if rc.document.approval_date else None,
    )


def build_and_persist(
    db: Session,
    user_id: str,
    question: str,
    retrieved: List[RetrievedChunk],
    llm_output: Dict,
) -> EvidencePackOut:
    citation_by_doc_id = {rc.document.id: build_citation(rc) for rc in retrieved}

    excerpts = []
    for e in llm_output.get("key_evidence_excerpts", []):
        cite = citation_by_doc_id.get(e.get("document_id"))
        if cite is None:
            continue
        excerpts.append(EvidenceExcerpt(
            document_id=e["document_id"],
            document_name=e.get("document_name", cite.document_name),
            excerpt=e.get("excerpt", ""),
            citation=cite,
        ))

    comparison_rows = []
    for row in llm_output.get("comparison_table", []):
        cite_a = citation_by_doc_id.get(row.get("source_a_document_id"))
        cite_b = citation_by_doc_id.get(row.get("source_b_document_id"))
        if not cite_a or not cite_b:
            continue
        comparison_rows.append(ComparisonRow(
            topic=row.get("topic", ""),
            source_a=row.get("source_a", ""),
            source_a_citation=cite_a,
            source_b=row.get("source_b", ""),
            source_b_citation=cite_b,
            note=row.get("note"),
        ))

    all_citations = list(citation_by_doc_id.values())

    pack_out = EvidencePackOut(
        id="",  # filled after DB insert
        question=question,
        research_summary=llm_output.get("research_summary", ""),
        relevant_rulings=llm_output.get("relevant_rulings", []),
        relevant_standards=llm_output.get("relevant_standards", []),
        key_evidence_excerpts=excerpts,
        comparison_table=comparison_rows,
        open_issues=llm_output.get("open_issues", []),
        citations=all_citations,
        conflict_flagged=bool(llm_output.get("conflict_flagged", False)),
        disclaimer=DISCLAIMER_TEXT,
        review_status=ReviewStatus.HUMAN_REVIEW_REQUIRED.value,  # FR-17: always defaults here
        is_fallback=False,
    )

    db_pack = EvidencePack(
        user_id=user_id,
        question=question,
        relevant_rulings=json.dumps(pack_out.relevant_rulings),
        relevant_standards=json.dumps(pack_out.relevant_standards),
        key_evidence_excerpts=json.dumps([x.model_dump() for x in excerpts]),
        comparison_table=json.dumps([x.model_dump() for x in comparison_rows]),
        open_issues=json.dumps(pack_out.open_issues),
        citations=json.dumps([c.model_dump() for c in all_citations]),
        research_summary=pack_out.research_summary,
        conflict_flagged="yes" if pack_out.conflict_flagged else "no",
        disclaimer=DISCLAIMER_TEXT,
        review_status=ReviewStatus.HUMAN_REVIEW_REQUIRED,
    )
    db.add(db_pack)
    db.commit()
    db.refresh(db_pack)

    pack_out.id = db_pack.id
    return pack_out
