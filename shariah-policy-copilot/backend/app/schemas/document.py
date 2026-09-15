from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentMetadataIn(BaseModel):
    document_name: str
    document_type: str
    version: str = "1.0"
    approval_status: str = "draft"  # approved|under_review|draft|archived
    approval_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    expiry_review_date: Optional[datetime] = None
    product_category: Optional[str] = None
    jurisdiction: Optional[str] = None
    approved_by: Optional[str] = None
    confidentiality_level: str = "internal"
    supersedes_document_id: Optional[str] = None


class DocumentOut(BaseModel):
    id: str
    document_name: str
    document_type: str
    version: str
    approval_status: str
    status_emoji: str
    approval_date: Optional[datetime]
    product_category: Optional[str]
    jurisdiction: Optional[str]
    is_current_version: int

    class Config:
        from_attributes = True
