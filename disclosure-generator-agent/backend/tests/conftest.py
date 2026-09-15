import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_AUDIT_LOG = PROJECT_ROOT / "data" / "test_audit.jsonl"
# Must be set before any `src.*` module is imported, since src/config.py
# reads the environment at import time.
os.environ.setdefault("AUDIT_LOG_PATH", str(TEST_AUDIT_LOG))

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from src.models.schemas import CalculationPayload
from src.signing.sign import sign_payload

KEYS_DIR = PROJECT_ROOT / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "dev_private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "dev_public_key.pem"


def _ensure_dev_keys() -> None:
    KEYS_DIR.mkdir(exist_ok=True)
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    private_key = Ed25519PrivateKey.generate()
    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY_PATH.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


_ensure_dev_keys()


@pytest.fixture(autouse=True)
def _clean_audit_log():
    if TEST_AUDIT_LOG.exists():
        TEST_AUDIT_LOG.unlink()
    yield


def default_payload(**overrides) -> CalculationPayload:
    data = dict(
        account_id="ACC-1001",
        account_name="Jane Doe",
        currency="USD",
        period_start="2026-06-01",
        period_end="2026-06-30",
        nav=1050000.75,
        opening_balance=1000000.00,
        closing_balance=1050000.75,
        return_percent=5.0,
        allocation=[
            {"category": "Equities", "weight_percent": 60.0},
            {"category": "Fixed Income", "weight_percent": 40.0},
        ],
        fees=[{"name": "Management Fee", "amount": 250.50, "currency": "USD"}],
    )
    data.update(overrides)
    return CalculationPayload(**data)


@pytest.fixture
def signer():
    return load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)


@pytest.fixture
def make_signed_run(signer):
    def _make(payload=None, run_id="RUN-0001", signed_at=None, **payload_overrides):
        payload = payload or default_payload(**payload_overrides)
        return sign_payload(run_id, payload, signer, signed_at=signed_at)

    return _make
