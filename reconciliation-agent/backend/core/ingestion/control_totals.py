"""Decimal import controls (§6.2), evaluated before any batch is committed.

Call once per account/statement. Different currencies are never netted.
This pure service returns a decision; persistence belongs to the importer.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Iterable

from core.ingestion.parsers.base import StatementBalance
from core.models.canonical_record import Direction


@dataclass(frozen=True)
class ControlRow:
    amount: Decimal
    direction: Direction
    currency: str


@dataclass(frozen=True)
class CurrencyTotals:
    row_count: int = 0
    debit_sum: Decimal = Decimal(0)
    credit_sum: Decimal = Decimal(0)


@dataclass(frozen=True)
class ControlReport:
    row_count: int
    currencies: dict[str, CurrencyTotals]
    errors: tuple[str, ...]

    @property
    def status(self) -> str:
        return "HELD" if self.errors else "VALIDATED"

    @property
    def break_code(self) -> str | None:
        return "DAT-04" if self.errors else None


def _valid_amount(value: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


def validate_control_totals(
    rows: Iterable[ControlRow],
    *,
    expected_row_count: int | None = None,
    expected_totals: dict[str, CurrencyTotals] | None = None,
    opening_balance: StatementBalance | None = None,
    closing_balance: StatementBalance | None = None,
) -> ControlReport:
    """Compare complete normalized rows with optional declared controls.

    An invalid row holds the whole batch and is still counted. A single
    supplied balance cannot establish balance continuity and also holds it.
    Currency totals supplied by a caller describe the entire statement.
    """
    errors: list[str] = []
    totals: dict[str, CurrencyTotals] = {}
    count = 0
    # Numeric(28,8) values summed at ordinary Decimal precision can round.
    with localcontext() as context:
        context.prec = 60
        for count, row in enumerate(rows, 1):
            if (not _valid_amount(row.amount)
                    or row.direction not in (Direction.DR, Direction.CR)
                    or not row.currency):
                errors.append(f"row {count}: invalid control value")
                continue
            previous = totals.get(row.currency, CurrencyTotals())
            totals[row.currency] = CurrencyTotals(
                previous.row_count + 1,
                previous.debit_sum + (row.amount if row.direction == Direction.DR else 0),
                previous.credit_sum + (row.amount if row.direction == Direction.CR else 0),
            )
        if expected_row_count is not None and count != expected_row_count:
            errors.append("declared row count does not match")
        if expected_totals is not None and totals != expected_totals:
            errors.append("declared currency totals do not match")
        if (opening_balance is None) != (closing_balance is None):
            errors.append("both opening and closing balances are required")
        elif opening_balance is not None and closing_balance is not None:
            balances = (opening_balance, closing_balance)
            if any(not _valid_amount(b.amount) or b.direction not in ("DR", "CR") for b in balances):
                errors.append("invalid statement balance")
            elif (not opening_balance.currency
                  or opening_balance.currency != closing_balance.currency
                  or set(totals) - {opening_balance.currency}):
                errors.append("statement balance currency does not match rows")
            elif opening_balance.as_of > closing_balance.as_of:
                errors.append("opening balance date is after closing balance date")
            else:
                movement = totals.get(opening_balance.currency, CurrencyTotals())
                opening = opening_balance.amount * (-1 if opening_balance.direction == "DR" else 1)
                closing = closing_balance.amount * (-1 if closing_balance.direction == "DR" else 1)
                if opening + movement.credit_sum - movement.debit_sum != closing:
                    errors.append("opening balance plus movement does not equal closing balance")
    return ControlReport(count, totals, tuple(errors))
