"""
Contract Analyzer — FastAPI backend.

Run (from backend/):
    uvicorn main:app --reload --port 8000

Then the React frontend (frontend/) talks to this API at
http://127.0.0.1:8000/api/analyze
"""

import os
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from extractor import analyze_contract_chunks, get_client
from ingestion import chunk_text, extract_text
from schemas import ContractAnalysis

app = FastAPI(title="Contract Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=ContractAnalysis)
async def analyze(contract: UploadFile = File(...)):
    ext = os.path.splitext(contract.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Upload a .pdf or .docx file.",
        )

    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)

    contents = await contract.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    try:
        text = extract_text(saved_path)
        if not text.strip():
            raise HTTPException(
                status_code=422,
                detail="No extractable text found. If this is a scanned PDF, it isn't supported yet.",
            )

        chunks = chunk_text(text)
        client = get_client()
        result = analyze_contract_chunks(chunks, client)
        return result

    except RuntimeError as e:
        # e.g. missing GEMINI_API_KEY
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong while analyzing: {e}")
    finally:
        if os.path.exists(saved_path):
            os.remove(saved_path)
