import numpy as np
import pandas as pd
import pytest

from sampling.audit_trail import AuditTrail
from sampling.challenge import apply_override, build_evidence, compare_items, ChallengeAction
from sampling.engine import SamplingPolicy, build_sample


def _population(n=100, seed=1):
    rng = np.random.default_rng(seed)
    ids = [f"I{i:05d}" for i in range(n)]
    amounts = np.round(rng.exponential(1000, n), 2)
    risk = rng.uniform(0, 100, n)
    return pd.DataFrame({"item_id": ids, "amount": amounts, "risk_score": risk})


def _sample():
    df = _population()
    policy = SamplingPolicy(
        policy_version="v1", tolerable_misstatement=50_000, confidence_level=0.95,
        random_control_size=10, high_risk_threshold=90,
    )
    result = build_sample(df, policy, risk_col="risk_score", user_seed="s1")
    return df, result


def test_non_selected_item_explanation_includes_probability_and_note():
    df, result = _sample()
    selected_ids = set(result.items["item_id"]) if len(result.items) else set()
    non_selected = df[~df["item_id"].isin(selected_ids)]
    assert len(non_selected) > 0
    item_id = non_selected.iloc[0]["item_id"]

    interval = result.manifest["mus_selection_metadata"].get("sampling_interval")
    evidence = build_evidence(item_id, df, result, sampling_interval=interval)

    assert evidence.selected is False
    assert "selection_probability" in evidence.facts
    assert any("not a conclusion" in w for w in evidence.warnings)


def test_judgmental_selection_warns():
    df, result = _sample()
    if "high_risk" not in result.strata or len(result.strata["high_risk"].items) == 0:
        pytest.skip("no high-risk items drawn in this sample")
    item_id = result.strata["high_risk"].items.iloc[0]["item_id"]
    evidence = build_evidence(item_id, df, result)
    assert evidence.selected is True
    assert any("judgmental" in w.lower() for w in evidence.warnings)


def test_comparison_shows_rule_differences():
    df, result = _sample()
    ids = list(result.items["item_id"])[:2]
    if len(ids) < 2:
        pytest.skip("not enough selected items")
    comparison = compare_items(ids[0], ids[1], df, result)
    assert "rules_only_in_a" in comparison
    assert "amount_difference" in comparison


def test_short_reason_raises(tmp_path):
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    with pytest.raises(ValueError):
        apply_override(
            trail, "auditor1", "item1", ChallengeAction.ACCEPT, "short",
            before={}, after={}, sampling_run_id="run1",
        )


def test_override_lands_in_trail_and_verifies(tmp_path):
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    result = apply_override(
        trail, "auditor1", "item1", ChallengeAction.REMOVE_FROM_SAMPLE,
        "removed due to immaterial duplicate transaction",
        before={"selected": True}, after={"selected": False}, sampling_run_id="run1",
    )
    assert "event_hash" in result
    report = trail.verify()
    assert report.valid is True
