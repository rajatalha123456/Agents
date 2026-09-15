from __future__ import annotations

from decimal import Decimal

import pytest

from core.ingestion.parsers.base import ParseError
from core.ingestion.parsers.mt940_parser import parse_mt940

SAMPLE_MT940 = """\
:20:REF001
:25:1234567890
:28C:1
:60F:C260101USD1000,00
:61:2601020102C50,00NTRFNONREF//ext-ref-1
:86:PAYMENT FROM JOHN DOE INV-100
:61:2601020102D25,50NTRFNONREF//ext-ref-2
:86:FEE CHARGE
:62F:C260102USD1024,50
-
"""


def test_parses_transactions():
    result = parse_mt940(SAMPLE_MT940.encode("utf-8"))
    assert result.source_format == "MT940"
    assert len(result.rows) == 2

    first = result.rows[0].fields
    assert first["status"] == "C"
    assert first["amount"] == "50.00"
    assert first["currency"] == "USD"
    assert first["value_date"] == "2026-01-02"
    assert first["bank_reference"] == "ext-ref-1"
    assert "INV-100" in first["narrative"]

    second = result.rows[1].fields
    assert second["status"] == "D"
    assert second["amount"] == "25.50"


def test_extracts_opening_and_closing_balance():
    result = parse_mt940(SAMPLE_MT940.encode("utf-8"))
    assert result.opening_balance.amount == Decimal("1000.00")
    assert result.opening_balance.currency == "USD"
    assert result.opening_balance.direction == "CR"
    assert result.closing_balance.amount == Decimal("1024.50")


def test_empty_file_raises():
    with pytest.raises(ParseError):
        parse_mt940(b"")


def test_garbage_raises_parse_error():
    with pytest.raises(ParseError):
        parse_mt940(b"this is not an mt940 statement at all, just prose text.")
