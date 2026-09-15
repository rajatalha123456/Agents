from decimal import Decimal

from core.close.certification import AccountCertificationFacts, can_certify, evaluate_certification


def clean_account(ref="ACC-1"):
    return AccountCertificationFacts(
        account_ref=ref, unexplained=Decimal("0"),
        has_high_risk_open_break=False, has_break_aged_past_policy_limit=False,
    )


def test_clean_period_can_certify():
    assert can_certify([clean_account()], Decimal("100")) is True


def test_unexplained_over_threshold_blocks():
    account = AccountCertificationFacts(
        account_ref="ACC-1", unexplained=Decimal("500"),
        has_high_risk_open_break=False, has_break_aged_past_policy_limit=False,
    )
    assert can_certify([account], Decimal("100")) is False


def test_high_risk_open_break_blocks():
    account = AccountCertificationFacts(
        account_ref="ACC-1", unexplained=Decimal("0"),
        has_high_risk_open_break=True, has_break_aged_past_policy_limit=False,
    )
    blockers = evaluate_certification([account], Decimal("100"))
    assert len(blockers) == 1
    assert "high-risk" in blockers[0].reason


def test_aged_item_past_policy_limit_blocks():
    account = AccountCertificationFacts(
        account_ref="ACC-1", unexplained=Decimal("0"),
        has_high_risk_open_break=False, has_break_aged_past_policy_limit=True,
    )
    assert can_certify([account], Decimal("100")) is False


def test_multiple_blockers_all_reported():
    account = AccountCertificationFacts(
        account_ref="ACC-1", unexplained=Decimal("999"),
        has_high_risk_open_break=True, has_break_aged_past_policy_limit=True,
    )
    blockers = evaluate_certification([account], Decimal("100"))
    assert len(blockers) == 3
