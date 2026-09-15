from datetime import date
from decimal import Decimal

import pytest

from core.ingestion.control_totals import ControlRow, CurrencyTotals, validate_control_totals
from core.ingestion.parsers.base import StatementBalance
from core.models.canonical_record import Direction


def row(amount, direction="CR", currency="USD"):
    return ControlRow(Decimal(amount), Direction(direction), currency)


def balance(amount, direction="CR", currency="USD"):
    return StatementBalance(Decimal(amount), currency, date(2026, 9, 1), direction)


def test_balanced_statement_with_debit_opening():
    result = validate_control_totals(
        [row("120"), row("10", "DR")], expected_row_count=2,
        opening_balance=balance("100", "DR"), closing_balance=balance("10"),
    )
    assert result.status == "VALIDATED"
    assert result.currencies == {"USD": CurrencyTotals(2, Decimal(10), Decimal(120))}


def test_balance_mismatch_holds_whole_batch():
    result = validate_control_totals([row("5")], opening_balance=balance("100"), closing_balance=balance("104"))
    assert result.status == "HELD"
    assert result.break_code == "DAT-04"


def test_currency_totals_do_not_net_across_currencies():
    result = validate_control_totals([row("5"), row("5", "DR", "EUR")])
    assert len(result.currencies) == 2
    assert result.currencies["USD"].credit_sum == Decimal(5)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1"])
def test_invalid_amount_is_counted_and_holds_batch(amount):
    result = validate_control_totals([row(amount), row("5")])
    assert result.status == "HELD"
    assert result.row_count == 2


def test_incomplete_balances_hold():
    assert validate_control_totals([], opening_balance=balance("0")).status == "HELD"


def test_cross_currency_statement_holds():
    assert validate_control_totals([row("5", currency="EUR")], opening_balance=balance("0"), closing_balance=balance("5")).status == "HELD"


def test_declared_controls_checked():
    assert validate_control_totals([row("1")], expected_row_count=2).status == "HELD"
    assert validate_control_totals([row("1")], expected_totals={}).status == "HELD"
    assert validate_control_totals([row("1")], expected_totals={"USD": CurrencyTotals(1, Decimal(0), Decimal(1))}).status == "VALIDATED"


def test_large_amounts_keep_fractional_precision():
    result = validate_control_totals([row("99999999999999999999.99999999")] * 2)
    assert result.currencies["USD"].credit_sum == Decimal("199999999999999999999.99999998")


def test_empty_statement():
    result = validate_control_totals(iter([]), expected_row_count=0, opening_balance=balance("10"), closing_balance=balance("10"))
    assert result.status == "VALIDATED"
    assert result.row_count == 0
