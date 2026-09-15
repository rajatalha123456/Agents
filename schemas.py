"""
Pydantic schemas for the Contract Analyzer agent.
These double as the JSON schema Gemini is forced to respond in
(structured output), so field descriptions matter — Gemini reads them.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class FeeItem(BaseModel):
    description: str = Field(description="What the fee/charge is for, e.g. 'Late payment penalty'")
    amount: Optional[str] = Field(default=None, description="Amount or rate as stated in the contract, e.g. '2% per month' or 'SAR 5,000'")
    trigger: Optional[str] = Field(default=None, description="Condition that triggers this fee, if any")


class LossClause(BaseModel):
    clause_type: str = Field(description="e.g. 'Indemnity', 'Limitation of Liability', 'Penalty', 'Force Majeure'")
    summary: str = Field(description="Plain-language summary of what the clause says")
    cap_or_limit: Optional[str] = Field(default=None, description="Any stated cap on liability/loss, if mentioned")
    source_reference: Optional[str] = Field(default=None, description="Clause/section number if identifiable")


class DateItem(BaseModel):
    label: str = Field(description="e.g. 'Effective Date', 'Expiry Date', 'Renewal Notice Deadline'")
    value: Optional[str] = Field(default=None, description="Date as stated in the contract (keep original format)")


class PSRDetails(BaseModel):
    applicable: bool = Field(description="Whether Payment Services Regulations (or equivalent payment-services compliance obligations) are referenced or relevant to this contract")
    parties: Optional[List[str]] = Field(default=None, description="Named parties / signatories to the contract")
    scope: Optional[str] = Field(default=None, description="Scope of payment services or responsibilities covered, if applicable")
    regulatory_notes: Optional[str] = Field(default=None, description="Any explicit reference to PSR / payment services regulation, licensing, or supervisory body")


class ConflictItem(BaseModel):
    clause_a: str = Field(description="First clause involved in the conflict (short quote or reference)")
    clause_b: str = Field(description="Second clause involved in the conflict")
    explanation: str = Field(description="Why these two clauses conflict or are inconsistent")
    severity: str = Field(description="One of: Low, Medium, High")


class ContractAnalysis(BaseModel):
    contract_type: str = Field(description="Classification, e.g. 'Loan Agreement', 'Lease', 'Master Service Agreement', 'NDA'")
    contract_type_confidence: str = Field(description="One of: Low, Medium, High")
    psr: PSRDetails
    fees: List[FeeItem] = Field(default_factory=list)
    loss_clauses: List[LossClause] = Field(default_factory=list)
    dates: List[DateItem] = Field(default_factory=list)
    conflicts: List[ConflictItem] = Field(default_factory=list)
    needs_human_review: bool = Field(description="True if any field was ambiguous, low-confidence, or the document was hard to parse")
    review_notes: Optional[str] = Field(default=None, description="Notes for the human reviewer, if needs_human_review is True")