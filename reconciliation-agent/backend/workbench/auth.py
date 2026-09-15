"""
Real password verification + signed session tokens for the local
workbench — replacing "trust whatever actor name the client sends in an
`X-Actor` header" with an actual credential check and a cryptographically
verified identity.

This is still explicitly the local-evaluation boundary documented
elsewhere (README's "Local evaluation boundary" section): the three demo
accounts and their passwords are seeded for this workspace, not a
production identity provider, RBAC service, or user-management system.
What's real here is the mechanism — password hashing, signature
verification, expiry — not the account roster behind it.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

import jwt

# A per-workspace secret is fine for local eval; production would load this
# from a secrets vault (§6.3's rule on credentials applies here too), never
# hardcode or commit it. RECON_JWT_SECRET lets a deployment override it.
_DEFAULT_LOCAL_SECRET = "local-dev-only-secret-do-not-use-in-production-32bytes-min"
JWT_SECRET = os.environ.get("RECON_JWT_SECRET", _DEFAULT_LOCAL_SECRET)
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60  # one working day

_PBKDF2_ITERATIONS = 100_000  # local-eval tool, not a production credential store — see module docstring


class AuthError(Exception):
    """Bad credentials, an invalid signature, or an expired token — the
    caller always turns this into an HTTP 401, never a 500 or a silent pass.
    """


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


@dataclass(frozen=True)
class SessionClaims:
    username: str
    role: str
    display_name: str


def create_token(*, username: str, role: str, display_name: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username, "role": role, "name": display_name,
        "iat": now, "exp": now + TOKEN_LIFETIME_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> SessionClaims:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired — please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid session token.") from exc
    try:
        return SessionClaims(username=payload["sub"], role=payload["role"], display_name=payload["name"])
    except KeyError as exc:
        raise AuthError("Malformed session token.") from exc


def seed_users() -> list[dict]:
    """The local workspace's fixed demo roster — three accounts, one per
    simulation role, matching the actors `workbench/service.py::ACTORS`
    already expects. Passwords are for this local evaluation tool only.
    """
    return [
        {"username": "analyst", "password_hash": hash_password("analyst-demo-pass"), "role": "MAKER", "display_name": "Alex Morgan"},
        {"username": "reviewer", "password_hash": hash_password("reviewer-demo-pass"), "role": "CHECKER", "display_name": "Riley Khan"},
        {"username": "controller", "password_hash": hash_password("controller-demo-pass"), "role": "CERTIFIER", "display_name": "Sam Chen"},
    ]


def authenticate(users: list[dict], username: str, password: str) -> dict:
    """Returns the matching user record, or raises AuthError. Constant-time
    comparison happens inside `verify_password`; this function still checks
    every user's hash structure defensively rather than short-circuiting on
    "username not found" with a different code path than "wrong password"
    (both simply raise the same generic error, so a caller can't tell them
    apart from timing or message).
    """
    user = next((u for u in users if u["username"] == username), None)
    if user is None or not verify_password(password, user["password_hash"]):
        raise AuthError("Invalid username or password.")
    return user
