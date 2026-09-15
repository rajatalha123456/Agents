"""
§6.1 — ISO 20022 CAMT.053 (and .052/.054, same `<Ntry>`/`<Bal>` shape)
bank statement parser. XPath is written against `local-name()` rather than
a pinned namespace URI, because CAMT ships in several schema versions
(001.02, 001.08, ...) that differ only in namespace/version, not in the
element names this parser reads.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from lxml import etree

from core.ingestion.parsers.base import ParsedFile, ParseError, RawRow, StatementBalance

_NTRY = ".//*[local-name()='Ntry']"


def _text(el: etree._Element, xpath: str) -> str:
    found = el.xpath(xpath)
    return found[0].text.strip() if found and found[0].text else ""


def _first(el: etree._Element, xpath: str):
    found = el.xpath(xpath)
    return found[0] if found else None


def _parse_balance(bal_el: etree._Element) -> StatementBalance | None:
    amt_el = _first(bal_el, ".//*[local-name()='Amt']")
    if amt_el is None or not amt_el.text:
        return None
    try:
        amount = Decimal(amt_el.text.strip())
    except InvalidOperation:
        return None
    currency = amt_el.get("Ccy", "")
    direction = _text(bal_el, ".//*[local-name()='CdtDbtInd']")
    date_text = _text(bal_el, ".//*[local-name()='Dt']/*[local-name()='Dt']") or _text(
        bal_el, ".//*[local-name()='Dt']"
    )
    from datetime import date as _date

    try:
        as_of = _date.fromisoformat(date_text[:10])
    except ValueError:
        return None
    return StatementBalance(
        amount=amount,
        currency=currency,
        as_of=as_of,
        direction="CR" if direction == "CRDT" else "DR",
    )


def _balance_by_code(root: etree._Element, code: str) -> StatementBalance | None:
    for bal_el in root.xpath(".//*[local-name()='Bal']"):
        bal_code = _text(bal_el, ".//*[local-name()='Cd']") or _text(bal_el, ".//*[local-name()='Prtry']")
        if bal_code == code:
            return _parse_balance(bal_el)
    return None


def parse_camt053(raw_bytes: bytes) -> ParsedFile:
    if not raw_bytes.strip():
        raise ParseError("file is empty")

    try:
        root = etree.fromstring(raw_bytes)
    except etree.XMLSyntaxError as exc:
        raise ParseError(f"could not parse CAMT.053 XML: {exc}") from exc

    entries = root.xpath(_NTRY)

    rows: list[RawRow] = []
    for line_no, entry in enumerate(entries, start=1):
        amount_text = _text(entry, "./*[local-name()='Amt']")
        amt_el = _first(entry, "./*[local-name()='Amt']")
        currency = amt_el.get("Ccy", "") if amt_el is not None else ""
        direction = _text(entry, "./*[local-name()='CdtDbtInd']")
        booking_date = _text(entry, "./*[local-name()='BookgDt']//*[local-name()='Dt']")
        value_date = _text(entry, "./*[local-name()='ValDt']//*[local-name()='Dt']")
        acct_svcr_ref = _text(entry, "./*[local-name()='AcctSvcrRef']")
        end_to_end_id = _text(entry, ".//*[local-name()='EndToEndId']")
        remittance = " ".join(
            t.strip()
            for t in entry.xpath(".//*[local-name()='Ustrd']/text()")
            if t and t.strip()
        )

        rows.append(
            RawRow(
                line_no=line_no,
                fields={
                    "amount": amount_text,
                    "currency": currency,
                    "direction": "CR" if direction == "CRDT" else "DR",
                    "booking_date": booking_date,
                    "value_date": value_date or booking_date,
                    "account_servicer_reference": acct_svcr_ref,
                    "end_to_end_id": end_to_end_id,
                    "narrative": remittance,
                },
            )
        )

    if not rows and not root.xpath(".//*[local-name()='Bal']"):
        raise ParseError("no recognizable CAMT.053 statement data found")

    return ParsedFile(
        rows=rows,
        opening_balance=_balance_by_code(root, "OPBD"),
        closing_balance=_balance_by_code(root, "CLBD"),
        source_format="CAMT053",
    )
