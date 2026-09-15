from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class QueryFilters(BaseModel):
    approved_only: bool = True          # FR-8 default scope
    current_version_only: bool = True   # FR-8 default scope
    product_category: Optional[str] = None
    document_type: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class QueryRequest(BaseModel):
    user_id: str
    question: str
    filters: QueryFilters = QueryFilters()
