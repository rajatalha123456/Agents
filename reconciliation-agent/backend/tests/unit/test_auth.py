from __future__ import annotations

import time

import jwt
import pytest

from workbench.auth import (
    AuthError,
    authenticate,
    create_token,
    decode_token,
    hash_password,
    seed_users,
    verify_password,
)


def test_hash_password_uses_a_per_call_salt():
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b  # different salts -> different stored hashes for the same password


def test_verify_password_accepts_the_correct_password():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored) is True


def test_verify_password_rejects_the_wrong_password():
    stored = hash_password("correct horse battery staple")
    assert verify_password("wrong password", stored) is False


def test_verify_password_rejects_a_malformed_stored_hash():
    assert verify_password("anything", "not-a-valid-stored-hash") is False


def test_create_and_decode_token_round_trip():
    token = create_token(username="analyst", role="MAKER", display_name="Alex Morgan")
    claims = decode_token(token)
    assert claims.username == "analyst"
    assert claims.role == "MAKER"
    assert claims.display_name == "Alex Morgan"


def test_decode_token_rejects_a_tampered_signature():
    token = create_token(username="analyst", role="MAKER", display_name="Alex Morgan")
    header, payload, signature = token.split(".")
    # Flip a character in the middle of the signature — flipping the very
    # last base64 character can decode to the same bits (base64's last
    # character in an incomplete group carries "don't care" padding bits),
    # so it isn't a reliable way to actually change the signature's bytes.
    mid = len(signature) // 2
    flipped_char = "A" if signature[mid] != "A" else "B"
    tampered_signature = signature[:mid] + flipped_char + signature[mid + 1:]
    tampered = f"{header}.{payload}.{tampered_signature}"
    with pytest.raises(AuthError):
        decode_token(tampered)


def test_decode_token_rejects_an_expired_token(monkeypatch):
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() - 100_000)
    token = create_token(username="analyst", role="MAKER", display_name="Alex Morgan")
    monkeypatch.setattr(time, "time", real_time)
    with pytest.raises(AuthError):
        decode_token(token)


def test_decode_token_rejects_a_token_signed_with_a_different_secret():
    forged = jwt.encode({"sub": "analyst", "role": "CERTIFIER", "name": "Not Alex"}, "some-other-secret", algorithm="HS256")
    with pytest.raises(AuthError):
        decode_token(forged)


def test_authenticate_succeeds_with_correct_credentials():
    users = seed_users()
    user = authenticate(users, "analyst", "analyst-demo-pass")
    assert user["role"] == "MAKER"


def test_authenticate_rejects_wrong_password():
    users = seed_users()
    with pytest.raises(AuthError):
        authenticate(users, "analyst", "wrong-password")


def test_authenticate_rejects_unknown_username():
    users = seed_users()
    with pytest.raises(AuthError):
        authenticate(users, "nobody", "anything")


def test_seed_users_covers_all_three_simulation_roles():
    roles = {u["role"] for u in seed_users()}
    assert roles == {"MAKER", "CHECKER", "CERTIFIER"}
