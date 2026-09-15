"""Object storage for uploaded dataset files.

Local-disk backend for now. The interface (save/open/delete keyed by an
opaque storage_key) is what a real deployment swaps for S3/GCS -- nothing
above this module should know or care which backend is in use.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("DATASET_STORAGE_ROOT", "./data/uploads")).resolve()
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def save_file(tenant_id: uuid.UUID | str, source_path: str, original_filename: str) -> str:
    """Copy a file into storage and return its storage_key."""
    key = f"{tenant_id}/{uuid.uuid4().hex}_{original_filename}"
    dest = STORAGE_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(source_path, "rb") as src, open(dest, "wb") as dst:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            dst.write(chunk)
    return key


def resolve_path(storage_key: str) -> str:
    path = (STORAGE_ROOT / storage_key).resolve()
    if STORAGE_ROOT not in path.parents and path != STORAGE_ROOT:
        raise ValueError("storage_key resolves outside the storage root")
    return str(path)


def delete_file(storage_key: str) -> None:
    path = resolve_path(storage_key)
    if os.path.exists(path):
        os.remove(path)
