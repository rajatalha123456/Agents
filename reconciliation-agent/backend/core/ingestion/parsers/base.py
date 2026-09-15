"""
§6 — the common shape every format parser produces, so the rest of the
ingestion pipeline (mapping, validation, control totals) never has to know
which source format a file came from. Deliberately has no dependency on
core.models: parsers run before anything is tenant-scoped or persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RawRow:
    """One row/entry exactly as the parser found it — unmapped, unvalidated."""

    line_no: int
    fields: dict[str, str]


@dataclass(frozen=True)
class StatementBalance:
    """
    §6.2 — a format-native declared balance (MT940 :60F:/:62F:, CAMT.053
    OPBD/CLBD). `direction` is a plain "CR"/"DR" string, not
    core.models.canonical_record.Direction — parsers stay model-free so
    they can be unit tested without importing the ORM.
    """

    amount: Decimal
    currency: str
    as_of: date
    direction: str


@dataclass(frozen=True)
class ParsedFile:
    """
    What every parser returns (§6.1). `opening_balance`/`closing_balance`
    are populated only by formats that natively declare them (MT940,
    CAMT.053) — None for CSV, which has no self-declared control total
    (§6.2's "extract ya calculate": these two fields are the "extract"
    half; core.ingestion.control_totals covers "calculate").
    """

    rows: list[RawRow]
    opening_balance: StatementBalance | None = None
    closing_balance: StatementBalance | None = None
    source_format: str = ""


class ParseError(Exception):
    """Raised when a file cannot be parsed at all (corrupt, wrong format, unreadable encoding)."""
