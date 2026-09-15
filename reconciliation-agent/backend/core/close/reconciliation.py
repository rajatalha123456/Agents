"""§15.2 — account-level reconciliation math: the arithmetic that turns
opening/movement/closing/explained into the `unexplained` figure, which is
the actual reconciliation output auditors care about. Kept as a pure
function so the identity is enforced in one place, not re-derived (and
possibly mis-derived) at every call site that touches an AccountReconciliation row.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AccountReconciliationFacts:
    opening_balance: Decimal
    movement: Decimal
    closing_balance: Decimal
    explained: Decimal


def compute_unexplained(facts: AccountReconciliationFacts) -> Decimal:
    """closing = opening + movement, in the absence of breaks; `explained`
    is how much of any gap between the statement/GL closing balance and
    (opening + movement) has been matched/resolved. What's left is unexplained.
    """
    expected_closing = facts.opening_balance + facts.movement
    gap = facts.closing_balance - expected_closing
    return gap - facts.explained
