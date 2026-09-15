"""
§6.1 — CSV/TSV parser. Delimiter and header detection are automatic
(§17.1: "System header detect karta hai"); column *meaning* is a mapping
studio concern (core/ingestion/mapping.py), not this module's — a CSV
parser has no idea which column is the amount.
"""
from __future__ import annotations

import csv
import io

from core.ingestion.parsers.base import ParsedFile, ParseError, RawRow

_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _decode(raw_bytes: bytes) -> str:
    for encoding in _ENCODINGS_TO_TRY:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file with any of the supported encodings")


def _sniff_dialect(sample: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel  # comma-delimited fallback


def parse_csv(raw_bytes: bytes) -> ParsedFile:
    text = _decode(raw_bytes)
    if not text.strip():
        raise ParseError("file is empty")

    dialect = _sniff_dialect(text[:4096])
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ParseError("no header row detected")
    reader.fieldnames = [name.strip() for name in reader.fieldnames]  # header already consumed above
    if any(not name for name in reader.fieldnames):
        raise ParseError("CSV headers must not be empty")
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ParseError("CSV headers must be unique")

    rows: list[RawRow] = []
    for line_no, raw_row in enumerate(reader, start=2):  # header was line 1
        if None in raw_row:
            raise ParseError(f"row {line_no} contains more values than the header declares")
        fields = {key: (value or "") for key, value in raw_row.items() if key is not None}
        rows.append(RawRow(line_no=line_no, fields=fields))

    return ParsedFile(rows=rows, source_format="CSV")
