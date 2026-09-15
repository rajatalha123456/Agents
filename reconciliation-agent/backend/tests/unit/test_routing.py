from decimal import Decimal

import pytest

from core.workflow.routing import RoutingRuleFacts, resolve_routing


def test_single_matching_rule_resolves():
    rules = [RoutingRuleFacts("AMT", None, None, "FINANCE_CHECKER", None, True)]
    decision = resolve_routing(break_family="AMT", amount=Decimal("100"), dimensions={}, rules=rules)
    assert decision.required_role == "FINANCE_CHECKER"
    assert decision.allow_auto_match is True


def test_no_matching_rule_raises():
    rules = [RoutingRuleFacts("AMT", None, None, "FINANCE_CHECKER", None, True)]
    with pytest.raises(ValueError):
        resolve_routing(break_family="SHA", amount=Decimal("1"), dimensions={}, rules=rules)


def test_amount_band_gte_gates_rule():
    rules = [
        RoutingRuleFacts("AMT", None, None, "FINANCE_CHECKER", None, True),
        RoutingRuleFacts("AMT", {"gte": 1_000_000}, None, "HEAD_OF_FINANCE", "HEAD_OF_FINANCE", True),
    ]
    low = resolve_routing(break_family="AMT", amount=Decimal("500"), dimensions={}, rules=rules)
    assert low.required_role == "FINANCE_CHECKER"
    high = resolve_routing(break_family="AMT", amount=Decimal("2000000"), dimensions={}, rules=rules)
    assert high.required_role == "HEAD_OF_FINANCE"


def test_allow_auto_match_false_always_wins():
    rules = [
        RoutingRuleFacts("SHA", None, None, "SHARIAH_SECRETARIAT", None, False),
        RoutingRuleFacts("SHA", None, None, "SOME_OTHER_ROLE", None, True),
    ]
    decision = resolve_routing(break_family="SHA", amount=None, dimensions={}, rules=rules)
    assert decision.allow_auto_match is False


def test_dimension_filter_excludes_non_matching_rule():
    rules = [
        RoutingRuleFacts("AMT", None, {"region": "US"}, "US_CHECKER", None, True),
        RoutingRuleFacts("AMT", None, None, "GLOBAL_CHECKER", None, True),
    ]
    decision = resolve_routing(break_family="AMT", amount=None, dimensions={"region": "EU"}, rules=rules)
    assert decision.required_role == "GLOBAL_CHECKER"
