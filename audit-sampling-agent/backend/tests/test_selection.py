import numpy as np
import pandas as pd
import pytest

from sampling.selection import (
    SelectionBasis,
    partition_population,
    select_monetary_unit,
    select_random,
    select_high_risk,
)
from sampling.determinism import dataset_fingerprint


def _population(n=200, seed=1):
    rng = np.random.default_rng(seed)
    ids = [f"I{i:05d}" for i in range(n)]
    amounts = np.round(rng.exponential(1000, n), 2)
    return pd.DataFrame({"item_id": ids, "amount": amounts})


def test_partition_population_splits_signs():
    df = pd.DataFrame({"item_id": ["a", "b", "c"], "amount": [100.0, -50.0, 0.0]})
    parts = partition_population(df, "item_id", "amount")
    assert len(parts["positive"]) == 1
    assert len(parts["negative"]) == 1
    assert len(parts["zero"]) == 1


def test_item_above_interval_flagged_certainty():
    df = _population(50)
    df.loc[0, "amount"] = 100_000.0  # far above any reasonable interval
    parts = partition_population(df, "item_id", "amount")
    fp = dataset_fingerprint(df, "item_id", "amount")
    selected, meta = select_monetary_unit(
        parts["positive"], sample_size=10, sampling_interval=2000,
        dataset_fingerprint_hex=fp, policy_version="v1",
    )
    certainty = selected[selected["_selection_basis"] == SelectionBasis.MUS_CERTAINTY.value]
    assert len(certainty) >= 1
    assert meta["certainty_items"] >= 1


def test_negative_and_zero_get_own_strata():
    df = pd.DataFrame({
        "item_id": [f"i{i}" for i in range(6)],
        "amount": [100.0, -100.0, 0.0, 200.0, -50.0, 0.0],
    })
    parts = partition_population(df, "item_id", "amount")
    assert len(parts["negative"]) == 2
    assert len(parts["zero"]) == 2


def test_high_risk_stratum_not_projectable():
    df = _population(50)
    df["risk_score"] = np.linspace(0, 100, 50)
    selected, meta = select_high_risk(df, risk_col="risk_score", threshold=90)
    assert meta["projectable"] is False
    assert SelectionBasis.HIGH_RISK.projectable is False


def test_no_item_appears_in_two_strata_mus_vs_random():
    df = _population(100)
    parts = partition_population(df, "item_id", "amount")
    fp = dataset_fingerprint(df, "item_id", "amount")
    mus_selected, _ = select_monetary_unit(
        parts["positive"], sample_size=20, sampling_interval=500,
        dataset_fingerprint_hex=fp, policy_version="v1",
    )
    exclude = set(mus_selected["item_id"])
    random_selected, _ = select_random(
        parts["positive"], sample_size=20, dataset_fingerprint_hex=fp,
        policy_version="v1", exclude_ids=exclude,
    )
    assert set(mus_selected["item_id"]).isdisjoint(set(random_selected["item_id"]))


def test_select_random_reproducible():
    df = _population(100)
    fp = dataset_fingerprint(df, "item_id", "amount")
    s1, _ = select_random(df, 10, fp, "v1", user_seed="x")
    s2, _ = select_random(df, 10, fp, "v1", user_seed="x")
    assert list(s1["item_id"]) == list(s2["item_id"])


def test_select_high_risk_requires_threshold_or_top_n():
    df = _population(10)
    df["risk_score"] = 50
    with pytest.raises(ValueError):
        select_high_risk(df, risk_col="risk_score")


def test_selection_basis_projectable_flags():
    assert SelectionBasis.MUS.projectable is True
    assert SelectionBasis.MUS_CERTAINTY.projectable is True
    assert SelectionBasis.RANDOM.projectable is True
    assert SelectionBasis.HIGH_RISK.projectable is False
    assert SelectionBasis.NEGATIVE_BALANCE.projectable is False
    assert SelectionBasis.ZERO_BALANCE.projectable is False
    assert SelectionBasis.AUDITOR_MANUAL.projectable is False
