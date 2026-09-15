import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.chunker import chunk_pages
from app.ingestion.loader import load_pages
from app.models.document import Document, DocumentChunk
from app.retrieval import vector_store
from app.schemas.document import DocumentMetadataIn


def ingest_document(db: Session, upload_path: str, original_filename: str, metadata: DocumentMetadataIn) -> Document:
    """Stores the source file, persists metadata + chunks, and embeds chunks into the vector store."""
    stored_path = _store_source_file(upload_path, original_filename)

    document = Document(
        document_name=metadata.document_name,
        document_type=metadata.document_type,
        version=metadata.version,
        approval_status=metadata.approval_status,
        approval_date=metadata.approval_date,
        effective_date=metadata.effective_date,
        expiry_review_date=metadata.expiry_review_date,
        product_category=metadata.product_category,
        jurisdiction=metadata.jurisdiction,
        approved_by=metadata.approved_by,
        confidentiality_level=metadata.confidentiality_level,
        source_file_path=stored_path,
    )

    # NFR-4: mark a superseded prior version as no longer current, keep it for historical search
    if metadata.supersedes_document_id:
        prior = db.query(Document).get(metadata.supersedes_document_id)
        if prior:
            prior.is_current_version = 0
        document.supersedes_document_id = metadata.supersedes_document_id

    db.add(document)
    db.flush()  # get document.id before chunking

    pages = load_pages(stored_path)
    raw_chunks = chunk_pages(pages)

    chunk_rows, chunk_ids, texts, metadatas = [], [], [], []
    for idx, rc in enumerate(raw_chunks):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=idx,
            section_label=rc.section_label,
            page_number=rc.page_number,
            text=rc.text,
        )
        db.add(chunk)
        chunk_rows.append(chunk)

    db.flush()  # get chunk ids

    for chunk in chunk_rows:
        chunk_ids.append(chunk.id)
        texts.append(chunk.text)
        metadatas.append({
            "document_id": document.id,
            "document_name": document.document_name,
            "version": document.version,
            "approval_status": metadata.approval_status,
            "is_current_version": document.is_current_version,
            "section_label": chunk.section_label or "",
            "page_number": chunk.page_number or 0,
        })

    if chunk_ids:
        vector_store.upsert_chunks(chunk_ids, texts, metadatas)

    db.commit()
    db.refresh(document)
    return document


def _store_source_file(upload_path: str, original_filename: str) -> str:
    dest_dir = Path(settings.raw_docs_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / original_filename
    shutil.copy(upload_path, dest)
    return str(dest)
