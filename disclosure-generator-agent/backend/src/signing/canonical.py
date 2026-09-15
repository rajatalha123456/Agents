"""Canonical byte representation of a run, shared by the signer and verifier.

Both sides MUST serialize identically or every signature will fail to
verify. Keeping this in one module (instead of duplicating the logic in
sign.py and verify.py) is what guarantees that.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def canonical_signing_bytes(run_id: str, payload: dict[str, Any], signed_at: datetime) -> bytes:
    """Deterministic JSON bytes for the (run_id, payload, signed_at) tuple.

    Sorted keys + compact separators + ISO-8601 timestamps make this stable
    across processes and languages, which real signing services will need.
    """
    obj = {
        "run_id": run_id,
        "payload": payload,
        "signed_at": signed_at.isoformat(),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
