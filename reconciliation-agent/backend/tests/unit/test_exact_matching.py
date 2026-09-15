from dataclasses import replace
from datetime import date
from decimal import Decimal

from core.matching.exact import MatchRecord, exact_pairs


def pair():
    a = MatchRecord("a", "SOURCE_A", "account", "USD", Decimal("10.00"), "CR", date(2026, 9, 1), "REF1")
    return a, replace(a, id="b", side="SOURCE_B", amount=Decimal("10"))


def test_equal_decimal_values_match():
    assert exact_pairs(list(pair())) == [("a", "b")]


def test_ambiguous_duplicate_never_matches():
    a, b = pair()
    assert exact_pairs([a, replace(a, id="a2"), b]) == []


def test_account_currency_date_direction_and_isolation_enforced():
    a, b = pair()
    for changed in [replace(b, account="other"), replace(b, currency="EUR"), replace(b, direction="DR"), replace(b, value_date=date(2026, 9, 2)), replace(b, isolation=("restricted",))]:
        assert exact_pairs([a, changed]) == []


def test_missing_references_do_not_match():
    a, b = pair()
    assert exact_pairs([replace(a, reference=""), replace(b, reference="")]) == []
