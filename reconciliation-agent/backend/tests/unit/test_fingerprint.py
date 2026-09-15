from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.models.canonical_record import Direction
from core.normalization.fingerprint import compute_row_fingerprint


def _fp(**overrides):
    base = dict(
        account_ref="ACC-1",
        amount=Decimal("100.00"),
        currency="USD",
        value_date=date(2026, 9, 1),
        reference_canonical="INV100",
        counterparty_id=None,
        direction=Direction.CR,
    )
    base.update(overrides)
    return compute_row_fingerprint(**base)


def test_deterministic():
    assert _fp() == _fp()


def test_sensitive_to_amount():
    assert _fp() != _fp(amount=Decimal("100.01"))


def test_sensitive_to_direction():
    assert _fp() != _fp(direction=Direction.DR)


def test_sensitive_to_account():
    assert _fp() != _fp(account_ref="ACC-2")


def test_no_ambiguous_concatenation_collision():
    # Without a separator, ("AB", "C") and ("A", "BC") would collide when
    # naively concatenated. The two computed here must differ.
    fp1 = compute_row_fingerprint(
        account_ref="AB", amount=Decimal("1"), currency="USD", value_date=date(2026, 1, 1),
        reference_canonical="C", counterparty_id=None, direction=Direction.CR,
    )
    fp2 = compute_row_fingerprint(
        account_ref="A", amount=Decimal("1"), currency="USD", value_date=date(2026, 1, 1),
        reference_canonical="BC", counterparty_id=None, direction=Direction.CR,
    )
    assert fp1 != fp2


def test_is_hex_sha256():
    fp = _fp()
    assert len(fp) == 64
    int(fp, 16)  # raises if not hex
