"""Central environment configuration. All values are read once at import time.

No secrets have hardcoded defaults. Values with a business/security meaning
(freshness window, key paths) fall back to development-safe defaults and
must be explicitly set in production.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    return int(value)


# --- LLM provider (Gemini only) ---
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")

LLM_TEMPERATURE = float(_env("LLM_TEMPERATURE", "0.1"))
LLM_TIMEOUT_SECONDS = _env_int("LLM_TIMEOUT_SECONDS", 60)

# --- Freshness ---
# 24 hours. Development default only — production must set this explicitly
# to match the business's actual acceptable staleness window.
MAX_RUN_AGE_SECONDS = _env_int("MAX_RUN_AGE_SECONDS", 86400)

# --- Signing keys (verification only; the Disclosure Generator never signs) ---
PUBLIC_KEY_PATH = _env("PUBLIC_KEY_PATH", str(PROJECT_ROOT / "keys" / "dev_public_key.pem"))

# Only used by the local reference signer (scripts/tests), never by the API.
PRIVATE_KEY_PATH = _env("PRIVATE_KEY_PATH", str(PROJECT_ROOT / "keys" / "dev_private_key.pem"))

# --- Audit log ---
AUDIT_LOG_PATH = _env("AUDIT_LOG_PATH", str(PROJECT_ROOT / "data" / "audit.jsonl"))

# --- Sanity validation ---
# Allocation weights must sum to 100% within this tolerance (percentage points).
ALLOCATION_SUM_TOLERANCE_PCT = float(_env("ALLOCATION_SUM_TOLERANCE_PCT", "0.5"))

# --- Dev tools (local testing frontend) ---
# Mounts POST /dev/sign, which signs an arbitrary caller-supplied payload
# with the local dev private key. NEVER enable this outside local
# development -- anyone who can reach it can forge validly-signed runs.
ENABLE_DEV_TOOLS = _env("ENABLE_DEV_TOOLS", "true").lower() == "true"

# Origins allowed to call this API via CORS (comma-separated). Needed only
# because the local test frontend (frontend/) runs on a different port.
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in _env("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()
]
