"""Deterministic, non-LLM verification that every number in generated text
traces back to a number already present in the verified payload.

Extraction & normalization rules
---------------------------------
1. A "number" is any token matching digit runs with optional thousands/
   decimal separators, ASCII (",", ".") or Arabic-Indic ("٬" U+066C
   thousands, "٫" U+066B decimal), with a leading "-" only recognized when
   NOT immediately preceded by a digit (so "2026-06-30" is read as three
   positive tokens 2026/06/30, not a negative six, while "-2.5%" in
   running text is read as negative). Digit characters themselves may be
   ASCII (0-9), Eastern Arabic-Indic (٠-٩), or Extended Arabic-Indic/Urdu
   (۰-۹) — Python's `\\d` and `decimal.Decimal` both handle these natively.
2. Thousands separators ("," or "٬") are stripped before parsing.
3. A trailing "%" or "٪" (Arabic percent sign) is stripped before parsing —
   the guard checks the numeric value only, not its unit, so "4.25" in the
   payload authorizes both "4.25" and "4.25%" in the text. Units are not
   this component's job; it only answers "does this number exist in the
   payload."
4. Values are compared as `decimal.Decimal`, so "1,000,000.50", "1000000.5",
   "1000000.50", and the Arabic-formatted "١٬٠٠٠٬٠٠٠٫٥" are all treated as
   the same number, and "06" and "6" are equal.
5. The payload's number set is built by recursively walking every leaf
   value (numbers, dates as ISO strings, and free-text string fields) and
   running the same extraction over each. This means a number embedded in
   a string field (including an adversarial one) is still "in the
   payload" if literally present there — the guard's only job is
   traceability to the signed payload, not judging intent.
6. Anything that fails to parse as a Decimal is ignored (not treated as
   a number, not treated as a violation) — ambiguous tokens are dropped
   rather than guessed about, per the fail-safe rule: reject only real
   mismatches, never invent a match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ARABIC_THOUSANDS_SEP = "٬"
ARABIC_DECIMAL_SEP = "٫"
ARABIC_PERCENT = "٪"

NUMBER_PATTERN = re.compile(
    rf"(?<!\d)-?\d[\d,{ARABIC_THOUSANDS_SEP}]*"
    rf"(?:[.{ARABIC_DECIMAL_SEP}]\d+)?[%{ARABIC_PERCENT}]?"
)


def _normalize(token: str) -> Decimal | None:
    t = token.strip().rstrip("%" + ARABIC_PERCENT)
    t = t.replace(",", "").replace(ARABIC_THOUSANDS_SEP, "")
    t = t.replace(ARABIC_DECIMAL_SEP, ".")
    if t in ("", "-", "."):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def extract_numbers(text: str) -> set[Decimal]:
    """Extract every numeric value present in a block of text."""
    numbers: set[Decimal] = set()
    for match in NUMBER_PATTERN.finditer(text):
        normalized = _normalize(match.group())
        if normalized is not None:
            numbers.add(normalized)
    return numbers


def _flatten_to_strings(value: object) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            texts.extend(_flatten_to_strings(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            texts.extend(_flatten_to_strings(v))
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float, Decimal)):
        texts.append(str(value))
    elif isinstance(value, (date, datetime)):
        texts.append(value.isoformat())
    elif isinstance(value, str):
        texts.append(value)
    return texts


def extract_payload_numbers(payload: dict) -> set[Decimal]:
    """Extract every numeric value present anywhere in the payload."""
    numbers: set[Decimal] = set()
    for text in _flatten_to_strings(payload):
        numbers |= extract_numbers(text)
    return numbers


@dataclass
class NumericGuardResult:
    passed: bool
    untraceable_numbers: list[str]
    generated_numbers: set[Decimal] = field(default_factory=set)
    payload_numbers: set[Decimal] = field(default_factory=set)


def check_numeric_guard(generated_text: str, payload: dict) -> NumericGuardResult:
    """Fail unless every number in `generated_text` exists in `payload`."""
    payload_numbers = extract_payload_numbers(payload)
    generated_numbers = extract_numbers(generated_text)

    untraceable = sorted(
        (n for n in generated_numbers if n not in payload_numbers), key=str
    )

    return NumericGuardResult(
        passed=len(untraceable) == 0,
        untraceable_numbers=[str(n) for n in untraceable],
        generated_numbers=generated_numbers,
        payload_numbers=payload_numbers,
    )
