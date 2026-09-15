"""Stable, tenant-scoped import identity (§6.2).

The importer must enforce the returned key with the ImportBatch unique
constraint inside its transaction; computing a key alone does not deduplicate.
"""
import hashlib
import json
from uuid import UUID


def import_identity(*, tenant_id: UUID, connector_id: UUID, raw_bytes: bytes, period: str) -> tuple[str, str]:
    """Return (file checksum, idempotency key) without ambiguous concatenation."""
    if not period or period != period.strip():
        raise ValueError("period must be a nonempty canonical identifier")
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    payload = json.dumps([str(tenant_id), str(connector_id), checksum, period], separators=(",", ":"))
    return checksum, hashlib.sha256(payload.encode("utf-8")).hexdigest()
