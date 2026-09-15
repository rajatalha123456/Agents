from typing import List, Optional

from pydantic import BaseModel


class Citation(BaseModel):
    document_id: str
    document_name: str
    version: str
    section_label: Optional[str] = None
    page_number: Optional[int] = None
    approval_date: Optional[str] = None


class EvidenceExcerpt(BaseModel):
    document_id: str
    document_name: str
    excerpt: str
    citation: Citation


class ComparisonRow(BaseModel):
    topic: str
    source_a: str
    source_a_citation: Citation
    source_b: str
    source_b_citation: Citation
    note: Optional[str] = None  # e.g. "CONFLICT" or "consistent"


class EvidencePackOut(BaseModel):
    id: str
    question: str
    research_summary: str
    relevant_rulings: List[str]
    relevant_standards: List[str]
    key_evidence_excerpts: List[EvidenceExcerpt]
    comparison_table: List[ComparisonRow]
    open_issues: List[str]
    citations: List[Citation]
    conflict_flagged: bool
    disclaimer: str
    review_status: str
    is_fallback: bool = False
