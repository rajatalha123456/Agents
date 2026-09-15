"""
§6.1 — BAI2 (Bank Administration Institute) statement parser. §27
positions BAI2 as "Should (v2) — US banks."

BAI2 is a flat, comma-delimited, record-code-driven format: one physical
line per record, each ending in a "/" terminator. This parser reads the
group ('02') and account ('03') header context as it walks the file so
each transaction detail ('16') row can carry its account/currency/as-of
date, then reshapes everything into the same format-neutral `RawRow` shape
every other parser produces — nothing downstream needs to know BAI2's
record-code grammar.

Row-level oddities (an unparsable amount, a garbled type code) are passed
through as raw strings rather than rejected here, exactly like the CSV
parser: this module only knows format *structure*, not field validity —
that's `workbench`/mapping-studio territory (§6.1, §17.1).
"""
from __future__ import annotations

from datetime import date

from core.ingestion.parsers.base import ParsedFile, ParseError, RawRow

_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_KNOWN_RECORD_CODES = {"01", "02", "03", "16", "49", "88", "98", "99"}


def _decode(raw_bytes: bytes) -> str:
    for encoding in _ENCODINGS_TO_TRY:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file with any of the supported encodings")


def _parse_yymmdd(value: str) -> date | None:
    value = value.strip()
    if len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
    year = 2000 + yy if yy < 80 else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _direction_for_type_code(type_code: str) -> str:
    # BAI2's type-code catalog groups 1xx-3xx as credit codes and 4xx-6xx
    # as debit codes; the leading digit is enough to classify without a
    # full lookup table (§6.1 doesn't require BAI2 transaction-type
    # semantics beyond sign, only that amount/direction reach the canonical
    # record correctly).
    return "CR" if type_code[:1] in ("1", "2", "3") else "DR"


def parse_bai2(raw_bytes: bytes) -> ParsedFile:
    text = _decode(raw_bytes)
    if not text.strip():
        raise ParseError("file is empty")

    lines = [line.strip().rstrip("/") for line in text.splitlines() if line.strip()]
    records = [line.split(",") for line in lines]
    codes_seen = {r[0].strip() for r in records if r and r[0].strip()}
    if not codes_seen & _KNOWN_RECORD_CODES:
        raise ParseError("no recognizable BAI2 record codes found")

    rows: list[RawRow] = []
    account = ""
    currency = ""
    as_of_date: date | None = None

    for line_no, fields in enumerate(records, start=1):
        code = fields[0].strip() if fields else ""

        if code == "02" and len(fields) > 4:
            as_of_date = _parse_yymmdd(fields[4])
            if len(fields) > 6:
                currency = fields[6].strip()
        elif code == "03" and len(fields) > 2:
            account = fields[1].strip()
            currency = fields[2].strip() or currency
        elif code == "16":
            type_code = fields[1].strip() if len(fields) > 1 else ""
            amount_raw = fields[2].strip() if len(fields) > 2 else ""
            amount = f"{amount_raw[:-2]}.{amount_raw[-2:]}" if amount_raw.isdigit() and len(amount_raw) > 2 else amount_raw
            rows.append(RawRow(
                line_no=line_no,
                fields={
                    "account": account,
                    "currency": currency,
                    "type_code": type_code,
                    "direction": _direction_for_type_code(type_code),
                    "amount": amount,
                    "value_date": as_of_date.isoformat() if as_of_date else "",
                    "funds_type": fields[3].strip() if len(fields) > 3 else "",
                    "bank_reference": fields[4].strip() if len(fields) > 4 else "",
                    "customer_reference": fields[5].strip() if len(fields) > 5 else "",
                    "narrative": ",".join(f.strip() for f in fields[6:]) if len(fields) > 6 else "",
                },
            ))
        elif code == "88" and rows:
            # Continuation of the previous 16 record's free-text narrative.
            extra = ",".join(f.strip() for f in fields[1:])
            previous = rows[-1].fields
            previous["narrative"] = (previous["narrative"] + " " + extra).strip()

    return ParsedFile(rows=rows, source_format="BAI2")
