"""§9.3 — the false-match circuit breaker. Automatic trip, human-only reset
(with a reason) — the plan is explicit that a human must acknowledge the
breach before auto-match resumes, so this module never re-arms itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.config import FalseMatchBudget


@dataclass(frozen=True)
class BreachEvent:
    metric: str
    observed: float
    target: float
    at: datetime


@dataclass
class CircuitBreakerState:
    """One instance per universe (§9.3 metrics are measured per universe).
    `tripped` starting False and only ever set True by `evaluate`, never by
    a constructor default someone forgot to override, keeps "armed by
    default" the only possible starting condition.
    """

    tripped: bool = False
    breach: BreachEvent | None = None
    reset_by: str | None = None
    reset_reason: str | None = None


@dataclass(frozen=True)
class ObservedMetrics:
    auto_match_false_rate: float
    suggest_acceptance_rate: float
    suggest_false_accept_rate: float
    calibration_ece: float


def evaluate(state: CircuitBreakerState, metrics: ObservedMetrics, budget: FalseMatchBudget, at: datetime) -> CircuitBreakerState:
    """Returns a new state. If already tripped, stays tripped — evaluate
    never clears a trip; only `reset` can, and only with a human + reason.
    """
    if state.tripped:
        return state

    checks = [
        ("auto_match_false_rate", metrics.auto_match_false_rate, budget.auto_match_false_rate_max, "gt"),
        ("calibration_ece", metrics.calibration_ece, budget.calibration_ece_max, "gt"),
        ("suggest_false_accept_rate", metrics.suggest_false_accept_rate, budget.suggest_false_accept_max, "gt"),
    ]
    for metric, observed, target, direction in checks:
        breached = observed > target if direction == "gt" else observed < target
        if breached:
            return CircuitBreakerState(
                tripped=True,
                breach=BreachEvent(metric=metric, observed=observed, target=target, at=at),
            )
    return state


class ResetWithoutReasonError(ValueError):
    pass


def reset(state: CircuitBreakerState, *, actor: str, reason: str) -> CircuitBreakerState:
    if not state.tripped:
        raise ValueError("circuit breaker is not tripped")
    if not reason:
        raise ResetWithoutReasonError("reset requires a reason (§9.3)")
    return CircuitBreakerState(tripped=False, breach=None, reset_by=actor, reset_reason=reason)
