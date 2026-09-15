"""Reference signing implementation.

IMPORTANT: This module conceptually belongs to the trusted calculation
engine / signing service, NOT to the Disclosure Generator. It exists here
only so tests and local development can produce validly signed runs
without a separate service. Production signing keys must never be
generated, stored, or used inside this application — see
scripts/generate_dev_keys.py and the README's production architecture
section.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.models.schemas import CalculationPayload, SignedRun
from src.signing.canonical import canonical_signing_bytes


def sign_payload(
    run_id: str,
    payload: CalculationPayload,
    private_key: Ed25519PrivateKey,
    signed_at: datetime | None = None,
) -> SignedRun:
    """Sign a calculation payload and return a complete SignedRun."""
    signed_at = signed_at or datetime.now(timezone.utc)
    payload_dict: dict[str, Any] = payload.model_dump(mode="json")

    message = canonical_signing_bytes(run_id, payload_dict, signed_at)
    signature_bytes = private_key.sign(message)
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

    return SignedRun(
        run_id=run_id,
        payload=payload,
        signature=signature_b64,
        signature_algorithm="Ed25519",
        signed_at=signed_at,
    )
