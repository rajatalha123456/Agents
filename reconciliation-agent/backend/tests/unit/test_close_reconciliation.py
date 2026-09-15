from decimal import Decimal

from core.close.reconciliation import AccountReconciliationFacts, compute_unexplained


def test_fully_explained_balance_yields_zero_unexplained():
    facts = AccountReconciliationFacts(
        opening_balance=Decimal("1000"), movement=Decimal("200"),
        closing_balance=Decimal("1250"), explained=Decimal("50"),
    )
    assert compute_unexplained(facts) == Decimal("0")


def test_unresolved_gap_is_unexplained():
    facts = AccountReconciliationFacts(
        opening_balance=Decimal("1000"), movement=Decimal("200"),
        closing_balance=Decimal("1250"), explained=Decimal("0"),
    )
    assert compute_unexplained(facts) == Decimal("50")


def test_no_gap_no_movement():
    facts = AccountReconciliationFacts(
        opening_balance=Decimal("1000"), movement=Decimal("0"),
        closing_balance=Decimal("1000"), explained=Decimal("0"),
    )
    assert compute_unexplained(facts) == Decimal("0")
