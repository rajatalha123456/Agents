"""
§7.1 — field-level normalization rules. Every function here is pure and
dependency-free beyond `dateutil` (already a core dependency): given a raw
value, either return the normalized form or raise `NormalizationError` with
a reason a caller can turn into a quarantine/DAT-0x break. Nothing here
touches the DB or knows about `dimensions` (EP-01) — those are ingestion
pipeline concerns (core/ingestion), not normalization-rule concerns.
"""
from __future__ import annotations

import enum
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as dateutil_parser

from core.models.canonical_record import Direction
from core.normalization.iso4217 import ISO_4217_CODES


class NormalizationError(ValueError):
    """Raised when a raw value cannot be normalized — the caller quarantines the row (§6.2/§7)."""


# --- Nulls (§7.1: "NULL, '', aur 'UNKNOWN' teeno alag represent hote hain") ---


class NullKind(str, enum.Enum):
    NULL = "NULL"  # the field was absent / None
    EMPTY = "EMPTY"  # the field was present but an empty string
    UNKNOWN_LITERAL = "UNKNOWN_LITERAL"  # the source literally wrote "UNKNOWN" (or a variant)
    VALUE = "VALUE"  # an actual, meaningful value


_UNKNOWN_LITERALS = {"unknown", "n/a", "na", "null"}


def classify_null(raw: str | None) -> NullKind:
    if raw is None:
        return NullKind.NULL
    stripped = raw.strip()
    if stripped == "":
        return NullKind.EMPTY
    if stripped.lower() in _UNKNOWN_LITERALS:
        return NullKind.UNKNOWN_LITERAL
    return NullKind.VALUE


# --- Date (posted_date / value_date never overwrite each other) ---


def normalize_date(raw: str | date | datetime, *, dayfirst: bool = False) -> date:
    """
    §7.1 — timezone-aware parse. Callers are responsible for keeping
    posted_date and value_date as two independent calls; this function has
    no notion of which field it's filling.
    """
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = raw.strip()
    if not text:
        raise NormalizationError("empty date")
    try:
        return dateutil_parser.parse(text, dayfirst=dayfirst).date()
    except (ValueError, OverflowError) as exc:
        raise NormalizationError(f"unparseable date {raw!r}: {exc}") from exc


# --- Amount + direction ---

_AMOUNT_CLEAN_RE = re.compile(r"[^\d,.\-]")
_TRAILING_SIGN_RE = re.compile(r"^(?P<num>.+?)(?P<sign>[+-])$")


def normalize_amount(
    raw: str | Decimal | int | float,
    *,
    explicit_direction: Direction | None = None,
) -> tuple[Decimal, Direction]:
    """
    §7.1 — "sign se direction derive hota hai; original sign convention
    preserve". Handles common bank-export sign conventions: a leading
    minus, a trailing minus (e.g. "50.00-"), and parenthesised negatives
    (e.g. "(50.00)"). Returns the absolute amount plus a derived
    `Direction` — callers that already know the direction from a separate
    column pass it as `explicit_direction`, which wins outright (a
    debit/credit column is a stronger signal than a sign character).
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, (int, float)):
        value = Decimal(str(raw))
    else:
        text = raw.strip()
        if not text:
            raise NormalizationError("empty amount")
        negative_parens = text.startswith("(") and text.endswith(")")
        if negative_parens:
            text = text[1:-1].strip()

        trailing = _TRAILING_SIGN_RE.match(text)
        trailing_sign = None
        if trailing:
            text = trailing.group("num")
            trailing_sign = trailing.group("sign")

        cleaned = _AMOUNT_CLEAN_RE.sub("", text)
        # Thousands separator vs decimal separator: if both , and . appear,
        # the last one is the decimal separator; if only , appears, treat
        # it as the decimal separator when it's the final one (e.g. "50,00").
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            whole, _, frac = cleaned.rpartition(",")
            cleaned = f"{whole.replace(',', '')}.{frac}" if len(frac) in (1, 2) else cleaned.replace(",", "")

        try:
            value = Decimal(cleaned)
        except InvalidOperation as exc:
            raise NormalizationError(f"unparseable amount {raw!r}") from exc

        if negative_parens or trailing_sign == "-":
            value = -abs(value)

    if explicit_direction is not None:
        return abs(value), explicit_direction

    return abs(value), Direction.CR if value >= 0 else Direction.DR


# --- Currency ---


def normalize_currency(raw: str) -> str:
    """§7.1 — ISO 4217 validate; unknown code = quarantine (raises here)."""
    code = raw.strip().upper()
    if code not in ISO_4217_CODES:
        raise NormalizationError(f"unknown ISO 4217 currency code {raw!r}")
    return code


# --- Reference ---

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def normalize_reference(raw: str) -> str:
    """§7.1 — reference_canonical = upper(strip_non_alnum(reference_raw))."""
    return _NON_ALNUM_RE.sub("", raw).upper()


# --- Counterparty ---

DEFAULT_LEGAL_SUFFIXES = (
    "LTD", "LIMITED", "LLC", "LLP", "PVT", "PRIVATE", "INC", "INCORPORATED",
    "CORP", "CORPORATION", "PLC", "GMBH", "SA", "NV", "BV", "CO",
)


def normalize_counterparty(raw: str, *, legal_suffixes: tuple[str, ...] = DEFAULT_LEGAL_SUFFIXES) -> str:
    """§7.1 — legal suffix strip from a *configurable* list; raw is preserved by the caller, not here."""
    collapsed = re.sub(r"\s+", " ", raw).strip()
    tokens = collapsed.split(" ")
    suffix_set = {s.upper().rstrip(".") for s in legal_suffixes}
    while tokens and tokens[-1].upper().rstrip(".,") in suffix_set:
        tokens.pop()
    return " ".join(tokens).strip(" .,")


# --- Description ---

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_description(raw: str) -> str:
    """§7.1 — control chars strip, whitespace collapse; raw is preserved by the caller, not here."""
    stripped = _CONTROL_CHAR_RE.sub("", unicodedata.normalize("NFKC", raw))
    return re.sub(r"\s+", " ", stripped).strip()
