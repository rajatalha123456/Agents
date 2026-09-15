from core.breaks.rollforward import is_carry_forward_eligible, roll_forward
from core.models.break_case import BreakCaseStatus as S


def test_roll_forward_preserves_age_and_increments_count():
    result = roll_forward(
        status=S.UNDER_REVIEW,
        carry_forward_count=1,
        age_days=45,
        original_period="2026-08",
        current_period="2026-09",
        escalation_threshold=3,
        high_risk_age_days=90,
    )
    assert result.status == S.CARRIED_FORWARD
    assert result.carry_forward_count == 2
    assert result.age_days == 45
    assert result.requires_escalation is False
    assert result.is_high_risk is False


def test_escalation_triggers_past_threshold():
    result = roll_forward(
        status=S.OPEN, carry_forward_count=3, age_days=10, original_period="2026-06",
        current_period="2026-09", escalation_threshold=3, high_risk_age_days=90,
    )
    assert result.requires_escalation is True


def test_high_risk_past_age_threshold():
    result = roll_forward(
        status=S.OPEN, carry_forward_count=0, age_days=91, original_period="2026-06",
        current_period="2026-09", escalation_threshold=3, high_risk_age_days=90,
    )
    assert result.is_high_risk is True


def test_closed_case_is_not_eligible_for_carry_forward():
    assert is_carry_forward_eligible(S.CLOSED) is False


def test_open_case_is_eligible_for_carry_forward():
    assert is_carry_forward_eligible(S.OPEN) is True
