import numpy as np
import pandas as pd
import pytest

from sampling.engine import SamplingPolicy, build_sample


def _population(n=300, seed=1):
    rng = np.random.default_rng(seed)
    ids = [f"I{i:05d}" for i in range(n)]
    amounts = np.round(rng.exponential(1000, n), 2)
    risk = rng.uniform(0, 100, n)
    return pd.DataFrame({"item_id": ids, "amount": amounts, "risk_score": risk})


def _policy(**overrides):
    base = dict(
        policy_version="v1", tolerable_misstatement=50_000, confidence_level=0.95,
        random_control_size=10,
    )
    base.update(overrides)
    return SamplingPolicy(**base)


def test_reproducible_across_shuffled_input():
    df = _population()
    policy = _policy()
    r1 = build_sample(df, policy, user_seed="s1")
    shuffled = df.sample(frac=1, random_state=99).reset_index(drop=True)
    r2 = build_sample(shuffled, policy, user_seed="s1")
    assert sorted(r1.items["item_id"]) == sorted(r2.items["item_id"])


def test_different_seed_gives_different_sample():
    df = _population()
    policy = _policy()
    r1 = build_sample(df, policy, user_seed="s1")
    r2 = build_sample(df, policy, user_seed="s2")
    assert sorted(r1.items["item_id"]) != sorted(r2.items["item_id"])


def test_no_item_selected_twice():
    df = _population()
    policy = _policy(high_risk_threshold=80)
    r = build_sample(df, policy, risk_col="risk_score", user_seed="s1")
    all_ids = list(r.items["item_id"])
    assert len(all_ids) == len(set(all_ids))


def test_capped_sample_size_produces_warning():
    df = _population(500)
    policy = _policy(max_sample_size=5)
    r = build_sample(df, policy, user_seed="s1")
    assert any("capped" in w.lower() for w in r.warnings)


def test_negative_and_zero_balances_covered_when_enabled():
    df = _population(50)
    df.loc[0, "amount"] = -500.0
    df.loc[1, "amount"] = 0.0
    policy = _policy(test_negative_balances_100pct=True, review_zero_balances=True)
    r = build_sample(df, policy, user_seed="s1")
    assert "negative_balances" in r.strata
    assert "zero_balances" in r.strata


def test_statistical_items_excludes_judgmental():
    df = _population(200)
    policy = _policy(high_risk_threshold=90)
    r = build_sample(df, policy, risk_col="risk_score", user_seed="s1")
    stat_ids = set(r.statistical_items["item_id"]) if len(r.statistical_items) else set()
    hr_ids = set(r.strata["high_risk"].items["item_id"]) if "high_risk" in r.strata else set()
    assert stat_ids.isdisjoint(hr_ids)
