from __future__ import annotations

import pytest

from core.ingestion.parsers.base import ParseError
from core.ingestion.parsers.csv_parser import parse_csv


def test_parses_comma_delimited():
    raw = b"Date,Amount,Reference\n2026-09-01,100.50,INV-1\n2026-09-02,-50.00,INV-2\n"
    result = parse_csv(raw)
    assert result.source_format == "CSV"
    assert len(result.rows) == 2
    assert result.rows[0].fields == {"Date": "2026-09-01", "Amount": "100.50", "Reference": "INV-1"}
    assert result.rows[0].line_no == 2
    assert result.rows[1].line_no == 3


def test_sniffs_semicolon_delimiter():
    raw = b"Date;Amount;Reference\n2026-09-01;100.50;INV-1\n"
    result = parse_csv(raw)
    assert result.rows[0].fields["Amount"] == "100.50"


def test_strips_header_whitespace():
    raw = b" Date , Amount \n2026-09-01,100.50\n"
    result = parse_csv(raw)
    assert set(result.rows[0].fields) == {"Date", "Amount"}


def test_handles_utf8_bom():
    raw = "Date,Amount\n2026-09-01,100.50\n".encode("utf-8-sig")
    result = parse_csv(raw)
    assert "Date" in result.rows[0].fields


def test_missing_trailing_value_becomes_empty_string():
    raw = b"Date,Amount,Reference\n2026-09-01,100.50\n"
    result = parse_csv(raw)
    assert result.rows[0].fields["Reference"] == ""


def test_empty_file_raises():
    with pytest.raises(ParseError):
        parse_csv(b"")


def test_header_only_no_rows():
    result = parse_csv(b"Date,Amount\n")
    assert result.rows == []
