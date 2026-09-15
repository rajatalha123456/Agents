from __future__ import annotations

import pytest

from core.ingestion.parsers.base import ParseError
from core.ingestion.parsers.bai2_parser import parse_bai2

SAMPLE_BAI2 = "\r\n".join([
    "01,SENDER,RECEIVER,260902,0800,0001,80,,2/",
    "02,RECEIVER,SENDER,1,260902,0800,USD,/",
    "03,1234567890,USD,010,150000,,/",
    "16,115,5000,,BANKREF1,CUSTREF1,PAYMENT FROM JOHN DOE/",
    "88,CONTINUED NARRATIVE TEXT/",
    "16,451,2500,,BANKREF2,CUSTREF2,SERVICE FEE/",
    "49,7500,3/",
    "98,7500,1,5/",
    "99,7500,1,7/",
]) + "\r\n"


def test_parses_transaction_details_with_account_and_date_context():
    result = parse_bai2(SAMPLE_BAI2.encode("utf-8"))
    assert result.source_format == "BAI2"
    assert len(result.rows) == 2
    first = result.rows[0].fields
    assert first["account"] == "1234567890"
    assert first["currency"] == "USD"
    assert first["value_date"] == "2026-09-02"
    assert first["amount"] == "50.00"
    assert first["direction"] == "CR"
    assert first["bank_reference"] == "BANKREF1"


def test_continuation_record_appends_to_previous_narrative():
    result = parse_bai2(SAMPLE_BAI2.encode("utf-8"))
    assert "PAYMENT FROM JOHN DOE" in result.rows[0].fields["narrative"]
    assert "CONTINUED NARRATIVE TEXT" in result.rows[0].fields["narrative"]


def test_debit_type_code_maps_to_dr():
    result = parse_bai2(SAMPLE_BAI2.encode("utf-8"))
    assert result.rows[1].fields["direction"] == "DR"
    assert result.rows[1].fields["amount"] == "25.00"


def test_empty_file_raises():
    with pytest.raises(ParseError):
        parse_bai2(b"")


def test_garbage_input_raises():
    with pytest.raises(ParseError):
        parse_bai2(b"this is not a BAI2 file at all\njust some text\n")


def test_headers_only_no_transactions_is_not_an_error():
    headers_only = "\r\n".join([
        "01,SENDER,RECEIVER,260902,0800,0001,80,,2/",
        "02,RECEIVER,SENDER,1,260902,0800,USD,/",
        "03,1234567890,USD,010,0,,/",
        "49,0,1/",
        "98,0,1,3/",
        "99,0,1,5/",
    ])
    result = parse_bai2(headers_only.encode("utf-8"))
    assert result.rows == []
