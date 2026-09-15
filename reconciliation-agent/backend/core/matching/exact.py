"""Unambiguous deterministic matching, with explicit isolation keys."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MatchRecord:
    id: str
    side: str
    account: str
    currency: str
    amount: Decimal
    direction: str
    value_date: date
    reference: str
    isolation: tuple[str, ...] = ()


def exact_pairs(records: list[MatchRecord]) -> list[tuple[str, str]]:
    """Only unique 1:1 keys qualify. Duplicates and empty references stay open.

    Caller scopes the input to one tenant, universe and period. Both sources
    must use the same configured debit/credit convention before this stage.
    """
    groups = defaultdict(lambda: {"SOURCE_A": [], "SOURCE_B": []})
    for row in records:
        if row.side not in ("SOURCE_A", "SOURCE_B"):
            raise ValueError("invalid source side")
        if not row.amount.is_finite() or row.amount < 0:
            raise ValueError("invalid amount")
        if not row.reference:
            continue
        key = (row.account, row.currency, row.amount, row.direction, row.value_date, row.reference, row.isolation)
        groups[key][row.side].append(row.id)
    return [(sides["SOURCE_A"][0], sides["SOURCE_B"][0]) for sides in groups.values()
            if len(sides["SOURCE_A"]) == len(sides["SOURCE_B"]) == 1]
