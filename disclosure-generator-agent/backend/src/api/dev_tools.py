"""DEV-ONLY endpoint for the local testing frontend.

NEVER enable this outside local development. `/dev/sign` signs whatever
payload the caller sends using the local dev private key (keys/dev_private_key.pem)
-- anyone who can reach it can forge validly-signed runs. It exists purely
so the frontend/ test console can produce signed runs without embedding a
private key in browser JS. Gate with ENABLE_DEV_TOOLS=false in any
shared/staging/production environment; src/api/main.py only mounts this
router when that flag is true.
"""
from __future__ import annotations

from datetime import datetime

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src import config
from src.models.schemas import CalculationPayload, SignedRun
from src.signing.sign import sign_payload

router = APIRouter(prefix="/dev", tags=["dev-only"])


class DevSignRequest(BaseModel):
    run_id: str = "DEV-RUN-0001"
    payload: CalculationPayload
    signed_at: datetime | None = None


@router.post("/sign", response_model=SignedRun)
def dev_sign(request: DevSignRequest) -> SignedRun:
    """Sign a payload with the local dev private key. Local testing only."""
    try:
        with open(config.PRIVATE_KEY_PATH, "rb") as f:
            private_key = load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Dev private key not found. Run scripts/generate_dev_keys.py first.",
        )

    return sign_payload(request.run_id, request.payload, private_key, signed_at=request.signed_at)
