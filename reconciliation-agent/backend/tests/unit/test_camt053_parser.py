from __future__ import annotations

from decimal import Decimal

import pytest

from core.ingestion.parsers.base import ParseError
from core.ingestion.parsers.camt053_parser import parse_camt053

SAMPLE_CAMT053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Id>STMT001</Id>
      <Acct><Id><IBAN>DE1234567890</IBAN></Id></Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2026-01-01</Dt></Dt>
      </Bal>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1024.50</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2026-01-02</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="EUR">50.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
        <BookgDt><Dt>2026-01-02</Dt></BookgDt>
        <ValDt><Dt>2026-01-02</Dt></ValDt>
        <AcctSvcrRef>ext-ref-1</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>INV-100</EndToEndId></Refs>
          <RmtInf><Ustrd>PAYMENT FROM JOHN DOE INV-100</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">25.50</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <Sts>BOOK</Sts>
        <BookgDt><Dt>2026-01-02</Dt></BookgDt>
        <ValDt><Dt>2026-01-02</Dt></ValDt>
        <AcctSvcrRef>ext-ref-2</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>FEE-1</EndToEndId></Refs>
          <RmtInf><Ustrd>FEE CHARGE</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def test_parses_entries():
    result = parse_camt053(SAMPLE_CAMT053.encode("utf-8"))
    assert result.source_format == "CAMT053"
    assert len(result.rows) == 2

    first = result.rows[0].fields
    assert first["amount"] == "50.00"
    assert first["currency"] == "EUR"
    assert first["direction"] == "CR"
    assert first["value_date"] == "2026-01-02"
    assert first["account_servicer_reference"] == "ext-ref-1"
    assert first["end_to_end_id"] == "INV-100"
    assert "INV-100" in first["narrative"]

    second = result.rows[1].fields
    assert second["direction"] == "DR"
    assert second["amount"] == "25.50"


def test_extracts_opening_and_closing_balance():
    result = parse_camt053(SAMPLE_CAMT053.encode("utf-8"))
    assert result.opening_balance.amount == Decimal("1000.00")
    assert result.opening_balance.currency == "EUR"
    assert result.closing_balance.amount == Decimal("1024.50")


def test_empty_file_raises():
    with pytest.raises(ParseError):
        parse_camt053(b"")


def test_malformed_xml_raises():
    with pytest.raises(ParseError):
        parse_camt053(b"<not><valid</xml")


def test_valid_xml_but_not_camt_raises():
    with pytest.raises(ParseError):
        parse_camt053(b"<root><unrelated>hello</unrelated></root>")
