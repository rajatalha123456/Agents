"""
SYNTHETIC DEMONSTRATION DATA for the P7 scoring/calibration screens.

Nothing in this module is derived from real match outcomes — §9.1's
isotonic calibration needs historical, human/assurance-reviewed match
dispositions (§9.4) to fit on, and this local workbench has none yet (no
pilot, no production usage). Every value this module produces is labeled
`synthetic: True` wherever it surfaces (API response, UI banner), the same
"explicitly synthetic, never silently presented as real" discipline the
sample workspace already follows for transaction data.

This module intentionally lives in `workbench/`, not `core/` — fabricated
data generation is a demo concern, not domain-agnostic engine logic.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from core.config import FalseMatchBudget
from core.matching.calibration import ConfidenceCalibrator, expected_calibration_error, reliability_diagram
from core.matching.circuit_breaker import CircuitBreakerState, ObservedMetrics, evaluate


def _synthetic_scores_and_labels(n: int, seed: int, overconfidence: float = 1.8) -> tuple[list[float], list[float]]:
    """A deliberately overconfident raw score (true positive probability is
    `raw ** overconfidence`, always <= raw) so the demo has something real
    to show calibration correcting — not just a trivially-already-perfect
    score.
    """
    rng = random.Random(seed)
    scores, labels = [], []
    for _ in range(n):
        raw = rng.random()
        true_p = raw**overconfidence
        scores.append(raw)
        labels.append(1.0 if rng.random() < true_p else 0.0)
    return scores, labels


def model_governance_snapshot() -> dict:
    """Fits on a synthetic train split, evaluates on a held-out synthetic
    test split (not the same rows — even a demo shouldn't grade on data it
    trained on), and runs the real §9.3 circuit breaker against a
    plausible healthy-state metrics reading.
    """
    train_scores, train_labels = _synthetic_scores_and_labels(240, seed=42)
    test_scores, test_labels = _synthetic_scores_and_labels(80, seed=99)

    calibrator = ConfidenceCalibrator()
    calibrator.fit(train_scores, train_labels)
    calibrated = [calibrator.predict(s) for s in test_scores]

    raw_ece = expected_calibration_error(test_scores, test_labels, test_scores)
    calibrated_ece = expected_calibration_error(test_scores, test_labels, calibrated)
    diagram = reliability_diagram(calibrated, test_labels)

    budget = FalseMatchBudget()
    metrics = ObservedMetrics(
        auto_match_false_rate=0.00004,
        suggest_acceptance_rate=0.86,
        suggest_false_accept_rate=0.003,
        calibration_ece=calibrated_ece,
    )
    breaker = evaluate(CircuitBreakerState(), metrics, budget, datetime.now(timezone.utc))

    return {
        "synthetic": True,
        "note": "Demonstration dataset — no real historical match dispositions exist yet in this local workspace.",
        "sample_size": {"train": len(train_scores), "test": len(test_scores)},
        "raw_ece": round(raw_ece, 4),
        "calibrated_ece": round(calibrated_ece, 4),
        "ece_target": budget.calibration_ece_max,
        "reliability_diagram": [
            {
                "bin_lower": round(b.bin_lower, 2), "bin_upper": round(b.bin_upper, 2),
                "mean_predicted": round(b.mean_predicted, 3), "observed_frequency": round(b.observed_frequency, 3),
                "count": b.count,
            }
            for b in diagram
        ],
        "circuit_breaker": {
            "tripped": breaker.tripped,
            "breach": None if not breaker.breach else {
                "metric": breaker.breach.metric, "observed": breaker.breach.observed, "target": breaker.breach.target,
            },
        },
        "false_match_budget": {
            "auto_match_false_rate_max": budget.auto_match_false_rate_max,
            "suggest_acceptance_rate_min": budget.suggest_acceptance_rate_min,
            "suggest_false_accept_max": budget.suggest_false_accept_max,
            "calibration_ece_max": budget.calibration_ece_max,
        },
        "observed_metrics": {
            "auto_match_false_rate": metrics.auto_match_false_rate,
            "suggest_acceptance_rate": metrics.suggest_acceptance_rate,
            "suggest_false_accept_rate": metrics.suggest_false_accept_rate,
        },
    }


def pilot_tenant_snapshot(state: dict) -> dict:
    """P9's pilot screen needs a tenant/customer and measured results that
    don't exist yet (§31 Q10 — no pilot customer has been chosen). This is
    a clearly-labeled dummy tenant record, not a real customer, so the
    screen has something concrete to render while genuinely reflecting
    that no real pilot has started: `is_dummy: True` throughout, and the
    "measured results" section reports real numbers already in `state`
    (imports/breaks/runs) rather than fabricating pilot KPIs that would be
    indistinguishable from real ones.
    """
    all_breaks = state.get("breaks", [])
    all_runs = state.get("runs", [])
    return {
        "is_dummy": True,
        "note": "No real pilot customer is onboarded yet (§31 Q10). This is a placeholder tenant record for the Pilot screen, not live customer data.",
        "tenant": {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "Northstar Demo Tenant",
            "status": "NOT_ONBOARDED",
            "base_currency": "USD",
            "timezone": "UTC",
        },
        # Everything below is real, drawn from this same local workspace's
        # actual state — not invented pilot metrics.
        "activity_to_date": {
            "imports": len(state.get("imports", [])),
            "breaks_created": len(all_breaks),
            "breaks_resolved": len([b for b in all_breaks if b["status"] in ("CLOSED", "RESOLVED")]),
            "agent_runs": len([r for r in all_runs if r["kind"] == "AGENT"]),
            "reconciliation_runs": len([r for r in all_runs if r["kind"] == "MATCHING"]),
        },
    }
