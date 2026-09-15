"""§16 — open-item roll-forward. An unresolved break carries into the next
period as the *same case* (same id, ageing continues) — it never becomes a
new case. Re-creating the case each period would reset age_days to 0 and
the ageing metric — the one auditors and regulators actually judge recon
quality on — would silently lie.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.breaks.lifecycle import IllegalTransition, TransitionRequest, transition
from core.models.break_case import BreakCaseStatus


@dataclass(frozen=True)
class RollForwardResult:
    status: BreakCaseStatus
    carry_forward_count: int
    age_days: int
    requires_escalation: bool
    is_high_risk: bool


def roll_forward(
    *,
    status: BreakCaseStatus,
    carry_forward_count: int,
    age_days: int,
    original_period: str | None,
    current_period: str,
    escalation_threshold: int,
    high_risk_age_days: int,
) -> RollForwardResult:
    """Called once per open case at period close. `age_days` must already
    reflect the elapsed time up to `current_period` — this function doesn't
    do date arithmetic, it only applies the roll-forward *rules* (§16).
    """
    new_status = transition(
        TransitionRequest(case_status=status, target=BreakCaseStatus.CARRIED_FORWARD, is_period_close=True)
    )
    new_count = carry_forward_count + 1
    return RollForwardResult(
        status=new_status,
        carry_forward_count=new_count,
        age_days=age_days,
        requires_escalation=new_count > escalation_threshold,
        is_high_risk=age_days > high_risk_age_days,
    )


def is_carry_forward_eligible(status: BreakCaseStatus) -> bool:
    try:
        transition(TransitionRequest(case_status=status, target=BreakCaseStatus.CARRIED_FORWARD, is_period_close=True))
        return True
    except IllegalTransition:
        return False
