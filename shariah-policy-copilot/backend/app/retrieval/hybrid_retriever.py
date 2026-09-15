"""Combines keyword + semantic search, and enforces the default retrieval scope. FR-7/FR-8/FR-9."""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document, DocumentChunk, ApprovalStatus
from app.retrieval import vector_store
from app.retrieval.keyword_search import keyword_search
from app.schemas.query import QueryFilters


@dataclass
class RetrievedChunk:
    chunk: DocumentChunk
    document: Document
    score_source: str  # "semantic" | "keyword" | "both"


def _candidate_documents(db: Session, filters: QueryFilters) -> List[Document]:
    q = db.query(Document)

    # FR-8: default scope = Approved + Current version only
    if filters.approved_only:
        q = q.filter(Document.approval_status == ApprovalStatus.APPROVED)
    if filters.current_version_only:
        q = q.filter(Document.is_current_version == 1)

    if filters.product_category:
        q = q.filter(Document.product_category == filters.product_category)
    if filters.document_type:
        q = q.filter(Document.document_type == filters.document_type)
    if filters.date_from:
        q = q.filter(Document.approval_date >= filters.date_from)
    if filters.date_to:
        q = q.filter(Document.approval_date <= filters.date_to)

    return q.all()


def retrieve(db: Session, question: str, filters: QueryFilters) -> List[RetrievedChunk]:
    candidate_docs = _candidate_documents(db, filters)
    if not candidate_docs:
        return []  # -> caller triggers FR-15 fallback

    doc_ids = [d.id for d in candidate_docs]
    docs_by_id = {d.id: d for d in candidate_docs}

    # --- Semantic search, scoped to the candidate document ids ---
    semantic_hits = vector_store.semantic_search(
        query=question,
        top_k=settings.top_k_semantic,
        where={"document_id": {"$in": doc_ids}},
    )
    semantic_chunk_ids = {h["chunk_id"] for h in semantic_hits}

    # --- Keyword search over the same candidate scope ---
    candidate_chunks: List[DocumentChunk] = (
        db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(doc_ids)).all()
    )
    keyword_hits = keyword_search(question, candidate_chunks, top_k=settings.top_k_keyword)
    keyword_chunk_ids = {c.id for c in keyword_hits}

    # --- Merge: union of both, tag overlap, cap at top_k_final ---
    chunks_by_id = {c.id: c for c in candidate_chunks}
    merged_ids = list(dict.fromkeys(list(semantic_chunk_ids) + list(keyword_chunk_ids)))  # semantic first

    results: List[RetrievedChunk] = []
    for cid in merged_ids[: settings.top_k_final]:
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            continue
        if cid in semantic_chunk_ids and cid in keyword_chunk_ids:
            source = "both"
        elif cid in semantic_chunk_ids:
            source = "semantic"
        else:
            source = "keyword"
        results.append(RetrievedChunk(chunk=chunk, document=docs_by_id[chunk.document_id], score_source=source))

    return results
