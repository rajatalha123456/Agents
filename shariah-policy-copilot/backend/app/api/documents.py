import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingestion.ingest_service import ingest_document
from app.models.document import ApprovalStatus, Document
from app.schemas.document import DocumentMetadataIn, DocumentOut
from app.utils.security import CurrentUser, get_current_user

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut)
def upload_document(
    file: UploadFile = File(...),
    document_name: str = Form(...),
    document_type: str = Form(...),
    version: str = Form("1.0"),
    approval_status: str = Form("draft"),
    product_category: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    approved_by: Optional[str] = Form(None),
    confidentiality_level: str = Form("internal"),
    supersedes_document_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """FR-1/FR-2/FR-3: ingest a source document with its metadata."""
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + file.filename) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    metadata = DocumentMetadataIn(
        document_name=document_name,
        document_type=document_type,
        version=version,
        approval_status=approval_status,
        product_category=product_category,
        jurisdiction=jurisdiction,
        approved_by=approved_by,
        confidentiality_level=confidentiality_level,
        supersedes_document_id=supersedes_document_id,
    )
    document = ingest_document(db, tmp_path, file.filename, metadata)
    return document


@router.get("", response_model=List[DocumentOut])
def list_documents(
    approval_status: Optional[str] = None,
    document_type: Optional[str] = None,
    product_category: Optional[str] = None,
    current_only: bool = True,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    q = db.query(Document)
    if approval_status:
        q = q.filter(Document.approval_status == ApprovalStatus(approval_status))
    if document_type:
        q = q.filter(Document.document_type == document_type)
    if product_category:
        q = q.filter(Document.product_category == product_category)
    if current_only:
        q = q.filter(Document.is_current_version == 1)
    return q.all()
