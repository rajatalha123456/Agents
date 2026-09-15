"""Signature, freshness, and sanity verification for signed calculation runs.

This is the Disclosure Generator's hard gate: nothing downstream (prompting,
generation, the numeric guard) ever runs on a run that fails here. Every
check is independent and all are evaluated, so a caller gets a complete
picture of what failed rather than just the first failure.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from src import config
from src.models.schemas import SignedRun
from src.signing.canonical import canonical_signing_bytes

ED25519_SIGNATURE_LENGTH = 64


@dataclass
class VerificationResult:
    signature_valid: bool
    freshness_valid: bool
    sanity_valid: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.signature_valid and self.freshness_valid and self.sanity_valid

    @property
    def reason(self) -> str | None:
        return "; ".join(self.reasons) if self.reasons else None


@lru_cache(maxsize=1)
def _load_public_key(public_key_path: str) -> Ed25519PublicKey:
    with open(public_key_path, "rb") as f:
        key = load_pem_public_key(f.read())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"Key at {public_key_path} is not an Ed25519 public key")
    return key


def _check_signature(signed_run: SignedRun, public_key: Ed25519PublicKey) -> tuple[bool, str | None]:
    if not signed_run.signature:
        return False, "signature is missing"

    try:
        signature_bytes = base64.b64decode(signed_run.signature, validate=True)
    except Exception:
        return False, "signature is not valid base64"

    if len(signature_bytes) != ED25519_SIGNATURE_LENGTH:
        return False, "signature has invalid length for Ed25519"

    if signed_run.signature_algorithm.lower() != "ed25519":
        return False, f"unsupported signature algorithm: {signed_run.signature_algorithm}"

    payload_dict = signed_run.payload.model_dump(mode="json")
    message = canonical_signing_bytes(signed_run.run_id, payload_dict, signed_run.signed_at)

    try:
        public_key.verify(signature_bytes, message)
    except InvalidSignature:
        return False, "signature verification failed (payload may have been tampered with)"

    return True, None


def _check_freshness(signed_run: SignedRun, max_age_seconds: int) -> tuple[bool, str | None]:
    signed_at = signed_run.signed_at
    if signed_at.tzinfo is None:
        signed_at = signed_at.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - signed_at).total_seconds()
    if age_seconds < 0:
        return False, "signed_at is in the future"
    if age_seconds > max_age_seconds:
        return False, f"run is stale ({age_seconds:.0f}s old, max {max_age_seconds}s)"
    return True, None


def _check_sanity(signed_run: SignedRun, tolerance_pct: float) -> tuple[bool, str | None]:
    payload = signed_run.payload

    if payload.period_start > payload.period_end:
        return False, "period_start is after period_end"

    total_weight = sum(item.weight_percent for item in payload.allocation)
    if abs(total_weight - 100.0) > tolerance_pct:
        return False, f"allocation weights sum to {total_weight:.2f}%, expected ~100%"

    if any(item.weight_percent < 0 for item in payload.allocation):
        return False, "allocation contains a negative weight"

    return True, None


def verify_signed_run(
    signed_run: SignedRun,
    public_key_path: str | None = None,
    max_age_seconds: int | None = None,
    tolerance_pct: float | None = None,
) -> VerificationResult:
    """Verify a signed run's signature, freshness, and payload sanity.

    Never raises for expected verification failures — callers check
    `.valid`. Only raises if verification itself cannot be performed
    (e.g. the public key file is missing/malformed), which is a
    configuration error, not a refusal.
    """
    public_key_path = public_key_path or config.PUBLIC_KEY_PATH
    max_age_seconds = max_age_seconds if max_age_seconds is not None else config.MAX_RUN_AGE_SECONDS
    tolerance_pct = tolerance_pct if tolerance_pct is not None else config.ALLOCATION_SUM_TOLERANCE_PCT

    public_key = _load_public_key(public_key_path)

    reasons: list[str] = []

    sig_valid, sig_reason = _check_signature(signed_run, public_key)
    if sig_reason:
        reasons.append(sig_reason)

    fresh_valid, fresh_reason = _check_freshness(signed_run, max_age_seconds)
    if fresh_reason:
        reasons.append(fresh_reason)

    sane_valid, sane_reason = _check_sanity(signed_run, tolerance_pct)
    if sane_reason:
        reasons.append(sane_reason)

    return VerificationResult(
        signature_valid=sig_valid,
        freshness_valid=fresh_valid,
        sanity_valid=sane_valid,
        reasons=reasons,
    )
