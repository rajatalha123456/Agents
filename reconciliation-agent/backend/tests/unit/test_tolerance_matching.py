from dataclasses import replace
from datetime import date
from decimal import Decimal

from core.matching.exact import MatchRecord
from core.matching.tolerance import ToleranceRule, tolerance_pairs

DAY_WINDOW = ToleranceRule(field="value_date", type="day_window", value=2)
AMOUNT_BAND = ToleranceRule(field="amount", type="absolute_or_percent", absolute=Decimal("5.00"))


def pair():
    a = MatchRecord("a", "SOURCE_A", "account", "USD", Decimal("100.00"), "CR", date(2026, 9, 1), "REF1")
    return a, replace(a, id="b", side="SOURCE_B")


def test_within_day_window_matches():
    a, b = pair()
    b = replace(b, value_date=date(2026, 9, 3))
    assert tolerance_pairs([a, b], [DAY_WINDOW]) == [("a", "b", ["value_date"])]


def test_outside_day_window_does_not_match():
    a, b = pair()
    b = replace(b, value_date=date(2026, 9, 5))
    assert tolerance_pairs([a, b], [DAY_WINDOW]) == []


def test_amount_within_absolute_band_matches():
    a, b = pair()
    b = replace(b, amount=Decimal("103.00"))
    assert tolerance_pairs([a, b], [AMOUNT_BAND]) == [("a", "b", ["amount"])]


def test_amount_outside_absolute_band_does_not_match():
    a, b = pair()
    b = replace(b, amount=Decimal("110.00"))
    assert tolerance_pairs([a, b], [AMOUNT_BAND]) == []


def test_ambiguous_candidate_pool_stays_open():
    a, b = pair()
    b2 = replace(b, id="b2")
    assert tolerance_pairs([a, b, b2], [DAY_WINDOW]) == []


def test_all_rules_must_pass():
    a, b = pair()
    b = replace(b, value_date=date(2026, 9, 3), amount=Decimal("103.00"))
    result = tolerance_pairs([a, b], [DAY_WINDOW, AMOUNT_BAND])
    assert result == [("a", "b", ["value_date", "amount"])]
