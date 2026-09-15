from datetime import datetime, timezone

import pytest

from core.config import FalseMatchBudget
from core.matching.circuit_breaker import (
    CircuitBreakerState,
    ObservedMetrics,
    ResetWithoutReasonError,
    evaluate,
    reset,
)

NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)
CLEAN = ObservedMetrics(0.0, 0.9, 0.001, 0.01)


def test_clean_metrics_do_not_trip():
    state = evaluate(CircuitBreakerState(), CLEAN, FalseMatchBudget(), NOW)
    assert state.tripped is False


def test_false_match_rate_breach_trips():
    metrics = ObservedMetrics(auto_match_false_rate=0.01, suggest_acceptance_rate=0.9,
                               suggest_false_accept_rate=0.001, calibration_ece=0.01)
    state = evaluate(CircuitBreakerState(), metrics, FalseMatchBudget(), NOW)
    assert state.tripped is True
    assert state.breach.metric == "auto_match_false_rate"


def test_calibration_ece_breach_trips():
    metrics = ObservedMetrics(0.0, 0.9, 0.001, calibration_ece=0.10)
    state = evaluate(CircuitBreakerState(), metrics, FalseMatchBudget(), NOW)
    assert state.tripped is True
    assert state.breach.metric == "calibration_ece"


def test_already_tripped_stays_tripped_even_if_metrics_recover():
    tripped = evaluate(CircuitBreakerState(), ObservedMetrics(0.01, 0.9, 0.001, 0.01), FalseMatchBudget(), NOW)
    still_tripped = evaluate(tripped, CLEAN, FalseMatchBudget(), NOW)
    assert still_tripped.tripped is True
    assert still_tripped is tripped


def test_reset_requires_reason():
    tripped = evaluate(CircuitBreakerState(), ObservedMetrics(0.01, 0.9, 0.001, 0.01), FalseMatchBudget(), NOW)
    with pytest.raises(ResetWithoutReasonError):
        reset(tripped, actor="admin", reason="")


def test_reset_clears_trip_with_reason():
    tripped = evaluate(CircuitBreakerState(), ObservedMetrics(0.01, 0.9, 0.001, 0.01), FalseMatchBudget(), NOW)
    cleared = reset(tripped, actor="admin", reason="investigated, false positive in test data")
    assert cleared.tripped is False
    assert cleared.reset_by == "admin"


def test_cannot_reset_when_not_tripped():
    with pytest.raises(ValueError):
        reset(CircuitBreakerState(), actor="admin", reason="n/a")
