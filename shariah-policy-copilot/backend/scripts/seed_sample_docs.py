"""Run: python -m scripts.seed_sample_docs

Creates two small sample text 'policies' — deliberately written to disagree on one
point — ingests them, and prints a sample query result so you can see the whole
pipeline (retrieval -> citation -> conflict flag -> disclaimer) working end to end.
"""
import tempfile
from datetime import datetime

from app.database import SessionLocal, init_db
from app.ingestion.ingest_service import ingest_document
from app.schemas.document import DocumentMetadataIn

DOC_A = """1. Late Payment Policy

1.1 Ta'widh on Late Payment

If a customer delays payment of Murabaha installments without valid excuse,
the institution may charge Ta'widh (compensation) calculated on actual loss
incurred, capped at the average cost of funds. Ta'widh amounts must be
credited to a charity account and never recognized as bank income.
"""

DOC_B = """1. Murabaha Product Guideline — Consumer Finance

1.1 Late Payment Charges

For consumer Murabaha late payments, a fixed penalty of 1% per month on the
overdue amount shall apply, credited to a dedicated welfare fund. This is
separate from Ta'widh and does not require proof of actual loss.
"""


def _write_temp(text: str) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
    f.write(text)
    f.close()
    return f.name


def main():
    init_db()
    db = SessionLocal()
    try:
        doc_a = ingest_document(
            db,
            upload_path=_write_temp(DOC_A),
            original_filename="board_resolution_ta_widh_v1.txt",
            metadata=DocumentMetadataIn(
                document_name="Board Resolution — Ta'widh on Late Payment",
                document_type="resolution",
                version="1.0",
                approval_status="approved",
                approval_date=datetime(2024, 3, 1),
                product_category="Murabaha",
                jurisdiction="SA",
                approved_by="Shariah Board",
            ),
        )
        doc_b = ingest_document(
            db,
            upload_path=_write_temp(DOC_B),
            original_filename="murabaha_consumer_guideline_v2.txt",
            metadata=DocumentMetadataIn(
                document_name="Murabaha Product Guideline — Consumer Finance",
                document_type="guideline",
                version="2.0",
                approval_status="approved",
                approval_date=datetime(2024, 6, 15),
                product_category="Murabaha",
                jurisdiction="SA",
                approved_by="Product & Shariah Committee",
            ),
        )
        print(f"Ingested: {doc_a.document_name} ({len(doc_a.chunks)} chunks)")
        print(f"Ingested: {doc_b.document_name} ({len(doc_b.chunks)} chunks)")
        print("\nNow POST to /query/ask with:")
        print('  {"user_id": "u1", "question": "What is the late payment charge for Murabaha?"}')
        print("You should see both documents cited and conflict_flagged=true.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
