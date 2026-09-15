from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.models.canonical_record import Direction
from core.normalization.rules import (
    NormalizationError,
    NullKind,
    classify_null,
    normalize_amount,
    normalize_counterparty,
    normalize_currency,
    normalize_date,
    normalize_description,
    normalize_reference,
)


class TestClassifyNull:
    def test_none_is_null(self):
        assert classify_null(None) == NullKind.NULL

    def test_empty_string_is_empty(self):
        assert classify_null("") == NullKind.EMPTY
        assert classify_null("   ") == NullKind.EMPTY

    def test_unknown_literal(self):
        assert classify_null("UNKNOWN") == NullKind.UNKNOWN_LITERAL
        assert classify_null("n/a") == NullKind.UNKNOWN_LITERAL

    def test_real_value(self):
        assert classify_null("ACME") == NullKind.VALUE


class TestNormalizeDate:
    def test_iso_date(self):
        assert normalize_date("2026-09-01") == date(2026, 9, 1)

    def test_slash_date_dayfirst(self):
        assert normalize_date("01/09/2026", dayfirst=True) == date(2026, 9, 1)

    def test_passthrough_date_object(self):
        assert normalize_date(date(2026, 1, 1)) == date(2026, 1, 1)

    def test_unparseable_raises(self):
        with pytest.raises(NormalizationError):
            normalize_date("not-a-date")

    def test_empty_raises(self):
        with pytest.raises(NormalizationError):
            normalize_date("")


class TestNormalizeAmount:
    def test_plain_positive(self):
        value, direction = normalize_amount("100.50")
        assert value == Decimal("100.50")
        assert direction == Direction.CR

    def test_leading_minus_is_debit(self):
        value, direction = normalize_amount("-100.50")
        assert value == Decimal("100.50")
        assert direction == Direction.DR

    def test_trailing_minus_is_debit(self):
        value, direction = normalize_amount("100.50-")
        assert value == Decimal("100.50")
        assert direction == Direction.DR

    def test_parens_negative_is_debit(self):
        value, direction = normalize_amount("(100.50)")
        assert value == Decimal("100.50")
        assert direction == Direction.DR

    def test_thousands_separator_comma(self):
        value, _ = normalize_amount("1,234.50")
        assert value == Decimal("1234.50")

    def test_european_decimal_comma(self):
        value, _ = normalize_amount("1.234,50")
        assert value == Decimal("1234.50")

    def test_explicit_direction_wins_over_sign(self):
        value, direction = normalize_amount("-50.00", explicit_direction=Direction.CR)
        assert value == Decimal("50.00")
        assert direction == Direction.CR

    def test_decimal_passthrough(self):
        value, direction = normalize_amount(Decimal("-5"))
        assert value == Decimal("5")
        assert direction == Direction.DR

    def test_empty_raises(self):
        with pytest.raises(NormalizationError):
            normalize_amount("")

    def test_garbage_raises(self):
        with pytest.raises(NormalizationError):
            normalize_amount("not-a-number")


class TestNormalizeCurrency:
    def test_valid_code(self):
        assert normalize_currency("usd") == "USD"

    def test_invalid_code_raises(self):
        with pytest.raises(NormalizationError):
            normalize_currency("XXX-NOT-REAL")


class TestNormalizeReference:
    def test_strips_and_upcases(self):
        assert normalize_reference("inv-2026/09-001") == "INV202609001"

    def test_empty(self):
        assert normalize_reference("") == ""


class TestNormalizeCounterparty:
    def test_strips_known_suffix(self):
        assert normalize_counterparty("Acme Widgets LTD") == "Acme Widgets"

    def test_strips_suffix_with_period(self):
        assert normalize_counterparty("Acme Inc.") == "Acme"

    def test_no_suffix_untouched(self):
        assert normalize_counterparty("Jane Doe") == "Jane Doe"

    def test_collapses_whitespace(self):
        assert normalize_counterparty("Acme    Widgets   LLC") == "Acme Widgets"

    def test_custom_suffix_list(self):
        assert normalize_counterparty("Acme Foo", legal_suffixes=("FOO",)) == "Acme"


class TestNormalizeDescription:
    def test_strips_control_chars(self):
        assert normalize_description("hello\x00world") == "helloworld"

    def test_collapses_whitespace(self):
        assert normalize_description("hello   \n\t world") == "hello world"
