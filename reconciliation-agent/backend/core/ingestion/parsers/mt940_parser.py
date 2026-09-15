"""
§6.1 — SWIFT MT940/MT942 statement parser. Delegates the tag grammar to
the `mt-940` library and reshapes its output into the format-neutral
`ParsedFile` shape (§6) — nothing downstream of this module needs to know
what a `:61:`/`:86:` field pair is.
"""
from __future__ import annotations

import mt940 as mt940_lib

from core.ingestion.parsers.base import ParsedFile, ParseError, RawRow, StatementBalance

_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _decode(raw_bytes: bytes) -> str:
    for encoding in _ENCODINGS_TO_TRY:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file with any of the supported encodings")


def _to_balance(balance: object | None) -> StatementBalance | None:
    if balance is None:
        return None
    return StatementBalance(
        amount=balance.amount.amount,
        currency=balance.amount.currency,
        as_of=balance.date,
        direction="CR" if balance.status == "C" else "DR",
    )


def parse_mt940(raw_bytes: bytes) -> ParsedFile:
    text = _decode(raw_bytes)
    if not text.strip():
        raise ParseError("file is empty")

    try:
        transactions = mt940_lib.parse(text)
    except Exception as exc:  # the mt-940 library raises a mix of its own + stdlib exceptions
        raise ParseError(f"could not parse MT940 statement: {exc}") from exc

    entries = list(transactions)
    # Unrecognized text parses "successfully" as a statement with no tags
    # at all rather than raising — that's indistinguishable from garbage
    # input, so treat it as one.
    if not entries and not transactions.data:
        raise ParseError("no recognizable MT940 statement data found")

    statement_reference = transactions.data.get("transaction_reference", "")
    account = transactions.data.get("account_identification", "")

    rows: list[RawRow] = []
    for line_no, tx in enumerate(entries, start=1):
        data = tx.data
        amount = data["amount"]
        rows.append(
            RawRow(
                line_no=line_no,
                fields={
                    "statement_reference": statement_reference,
                    "account": account,
                    "status": data.get("status", ""),  # raw :61: C/D mark
                    "direction": "CR" if data.get("status") == "C" else "DR",  # canonical form of the same mark
                    "amount": str(abs(amount.amount)),
                    "currency": amount.currency,
                    "value_date": data["date"].isoformat() if data.get("date") else "",
                    "entry_date": data["entry_date"].isoformat() if data.get("entry_date") else "",
                    "bank_reference": data.get("bank_reference") or "",
                    "customer_reference": data.get("customer_reference") or "",
                    "narrative": data.get("transaction_details", "") or "",
                    "id": data.get("id", "") or "",
                },
            )
        )

    return ParsedFile(
        rows=rows,
        opening_balance=_to_balance(transactions.data.get("final_opening_balance")),
        closing_balance=_to_balance(transactions.data.get("final_closing_balance")),
        source_format="MT940",
    )
