import base64
from datetime import datetime, timedelta, timezone

from src.signing.verify import verify_signed_run


def test_valid_signature_passes(make_signed_run):
    signed_run = make_signed_run()
    result = verify_signed_run(signed_run)
    assert result.valid
    assert result.signature_valid
    assert result.freshness_valid
    assert result.sanity_valid


def test_tampered_payload_fails(make_signed_run):
    signed_run = make_signed_run()
    signed_run.payload.nav = signed_run.payload.nav + 1000
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.signature_valid


def test_missing_signature_fails(make_signed_run):
    signed_run = make_signed_run()
    signed_run.signature = ""
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.signature_valid


def test_invalid_signature_fails(make_signed_run):
    signed_run = make_signed_run()
    signed_run.signature = base64.b64encode(b"\x00" * 64).decode("ascii")
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.signature_valid


def test_malformed_signature_fails(make_signed_run):
    signed_run = make_signed_run()
    signed_run.signature = "not-valid-base64!!!"
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.signature_valid


def test_stale_run_fails(make_signed_run):
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    signed_run = make_signed_run(signed_at=old_time)
    result = verify_signed_run(signed_run, max_age_seconds=3600)
    assert not result.valid
    assert not result.freshness_valid
    # A stale run's signature is still cryptographically valid.
    assert result.signature_valid


def test_future_signed_at_fails(make_signed_run):
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    signed_run = make_signed_run(signed_at=future_time)
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.freshness_valid


def test_invalid_allocation_sum_fails(make_signed_run):
    signed_run = make_signed_run(
        allocation=[
            {"category": "Equities", "weight_percent": 50.0},
            {"category": "Fixed Income", "weight_percent": 20.0},
        ]
    )
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.sanity_valid
    assert result.signature_valid


def test_negative_allocation_weight_fails(make_signed_run):
    signed_run = make_signed_run(
        allocation=[
            {"category": "Equities", "weight_percent": 120.0},
            {"category": "Fixed Income", "weight_percent": -20.0},
        ]
    )
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.sanity_valid


def test_period_start_after_period_end_fails(make_signed_run):
    signed_run = make_signed_run(period_start="2026-07-01", period_end="2026-06-01")
    result = verify_signed_run(signed_run)
    assert not result.valid
    assert not result.sanity_valid


def test_allocation_within_tolerance_passes(make_signed_run):
    signed_run = make_signed_run(
        allocation=[
            {"category": "Equities", "weight_percent": 60.2},
            {"category": "Fixed Income", "weight_percent": 39.6},
        ]
    )
    result = verify_signed_run(signed_run, tolerance_pct=0.5)
    assert result.sanity_valid
