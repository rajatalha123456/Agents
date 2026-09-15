"""Disk-backed, resumable uploads and a durable single-worker queue."""

import hashlib
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter()
DATA_DIR = Path(os.getenv("ANOMALY_JOB_DIR", ".data/jobs"))
MAX_FILE_BYTES = int(os.getenv("ANOMALY_MAX_FILE_BYTES", str(64 * 1024**3)))
CHUNK_BYTES = 8 * 1024**2
DISK_RESERVE_BYTES = int(os.getenv("ANOMALY_DISK_RESERVE_BYTES", str(1024**3)))


def job_dir(job_id):
    try:
        if str(UUID(job_id)) != job_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "Invalid upload id.")
    return DATA_DIR / job_id


@contextmanager
def database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "queue.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, size INTEGER NOT NULL,
            received INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'uploading',
            rows_done INTEGER NOT NULL DEFAULT 0, batches_done INTEGER NOT NULL DEFAULT 0,
            error TEXT, created REAL NOT NULL, updated REAL NOT NULL)""")
        db.commit()
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_job(db, job_id):
    job_dir(job_id)
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Upload not found.")
    return dict(row)


def public_job(job):
    return {**job, "chunk_bytes": CHUNK_BYTES,
            "analysis_id": job["id"] if job["state"] == "completed" else None}


class NewUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=2**53 - 1)


@router.get("/anomaly/upload-config")
def upload_config():
    return {"max_file_bytes": MAX_FILE_BYTES, "chunk_bytes": CHUNK_BYTES,
            "formats": ["csv", "json", "jsonl", "ndjson"]}


@router.post("/anomaly/uploads", status_code=201)
def create_upload(body: NewUpload):
    if Path(body.filename).suffix.lower() not in {".csv", ".json", ".jsonl", ".ndjson"}:
        raise HTTPException(400, "Use CSV, JSON or JSONL.")
    if MAX_FILE_BYTES and body.size > MAX_FILE_BYTES:
        raise HTTPException(413, "File exceeds this deployment's configured upload capacity.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        reserved = db.execute("SELECT COALESCE(SUM(size-received),0) FROM jobs WHERE state='uploading'").fetchone()[0]
        if body.size + reserved + DISK_RESERVE_BYTES > shutil.disk_usage(DATA_DIR).free:
            raise HTTPException(507, "Insufficient disk space for this upload. Free storage or cancel unused uploads.")
        job_id = str(uuid4())
        now = time.time()
        directory = job_dir(job_id)
        directory.mkdir()
        (directory / "source").touch()
        db.execute("INSERT INTO jobs(id,filename,size,created,updated) VALUES(?,?,?,?,?)",
                   (job_id, Path(body.filename).name, body.size, now, now))
        return public_job(get_job(db, job_id))


@router.get("/anomaly/uploads/{job_id}")
def upload_status(job_id: str):
    with database() as db:
        return public_job(get_job(db, job_id))


@router.post("/anomaly/uploads/{job_id}/chunks")
def append_chunk(job_id: str, offset: int, file: UploadFile = File(...)):
    # Each request is small; the entire source is never read into RAM.
    content = file.file.read(CHUNK_BYTES + 1)
    if not content or len(content) > CHUNK_BYTES:
        raise HTTPException(413, "Chunk must contain 1 byte to 8 MiB.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        job = get_job(db, job_id)
        if job["state"] != "uploading":
            raise HTTPException(409, "Upload is no longer accepting chunks.")
        path = job_dir(job_id) / "source"
        if offset < 0 or offset > job["received"] or offset + len(content) > job["size"]:
            raise HTTPException(409, "Chunk offset does not match the uploaded file.")
        with path.open("r+b") as output:
            output.seek(offset)
            if offset < job["received"]:
                if offset + len(content) > job["received"] or hashlib.sha256(output.read(len(content))).digest() != hashlib.sha256(content).digest():
                    raise HTTPException(409, "Retry content differs from the stored chunk.")
                return public_job(job)
            if shutil.disk_usage(DATA_DIR).free < len(content) + DISK_RESERVE_BYTES:
                raise HTTPException(507, "Disk is full. Upload can resume after storage is freed.")
            output.write(content)
            output.truncate()
            output.flush()
            os.fsync(output.fileno())
        db.execute("UPDATE jobs SET received=?,updated=? WHERE id=?",
                   (offset + len(content), time.time(), job_id))
        return public_job(get_job(db, job_id))


@router.post("/anomaly/uploads/{job_id}/complete")
def complete_upload(job_id: str):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        job = get_job(db, job_id)
        if job["state"] in {"queued", "processing", "completed"}:
            return public_job(job)
        if job["state"] != "uploading" or job["received"] != job["size"]:
            raise HTTPException(409, "Upload all bytes before starting analysis.")
        if (job_dir(job_id) / "source").stat().st_size != job["size"]:
            raise HTTPException(409, "Stored upload size does not match. Upload again.")
        db.execute("UPDATE jobs SET state='queued',updated=? WHERE id=?", (time.time(), job_id))
        return public_job(get_job(db, job_id))


@router.delete("/anomaly/uploads/{job_id}")
def cancel_upload(job_id: str):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        job = get_job(db, job_id)
        if job["state"] == "completed":
            raise HTTPException(409, "Completed analysis is retained in history.")
        # The worker acknowledges cancellation and removes its own files.
        state = "cancelling" if job["state"] in {"processing", "cancelling"} else "cancelled"
        db.execute("UPDATE jobs SET state=?,updated=? WHERE id=?", (state, time.time(), job_id))
        if state == "cancelled":
            for name in ("source", "findings.jsonl", "findings.partial"):
                (job_dir(job_id) / name).unlink(missing_ok=True)
        return public_job(get_job(db, job_id))


@router.get("/anomaly/uploads/{job_id}/findings")
def download_findings(job_id: str):
    with database() as db:
        job = get_job(db, job_id)
        if job["state"] != "completed":
            raise HTTPException(409, "Findings are available after analysis completes.")
    return FileResponse(job_dir(job_id) / "findings.jsonl", media_type="application/x-ndjson",
                        filename=f"{job_id}-findings.jsonl")
