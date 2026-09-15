import numpy as np
import pandas as pd
import pytest

from sampling.anomaly import EnsembleConfig, detect_anomalies, robust_z_scores


def _features(n=200, seed=1, with_outliers=True):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "amount": rng.normal(1000, 100, n),
        "count": rng.poisson(5, n).astype(float),
    })
    if with_outliers:
        df.loc[0, "amount"] = 100_000.0
        df.loc[1, "count"] = 500.0
    return df


def test_injected_outliers_rank_highest():
    df = _features()
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    top_indices = np.argsort(-result.scores)[:5]
    assert 0 in top_indices or 1 in top_indices


def test_effective_weights_sum_to_one():
    df = _features(300)
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    total = sum(d.weight_effective for d in result.detectors)
    assert total == pytest.approx(1.0, abs=1e-9)


def test_missing_temporal_redistributes_weights():
    df = _features(300)
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    weights = {d.name: d.weight_effective for d in result.detectors}
    assert weights["temporal"] == 0.0
    # 0.35 / 0.80 = 0.4375
    assert weights["isolation_forest"] == pytest.approx(0.35 / 0.80, abs=1e-6)


def test_scores_span_0_100():
    df = _features(300)
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    assert result.scores.min() >= 0
    assert result.scores.max() <= 100


def test_identical_seeds_give_identical_scores():
    df = _features(300)
    r1 = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    r2 = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    assert np.allclose(r1.scores, r2.scores)


def test_constant_column_produces_no_infinities():
    df = pd.DataFrame({"amount": [100.0] * 100, "count": np.random.default_rng(0).normal(5, 1, 100)})
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    assert np.isfinite(result.scores).all()


def test_small_population_skips_model_detectors():
    df = _features(10)
    result = detect_anomalies(df, dataset_fingerprint_hex="fp", user_seed="s1")
    by_name = {d.name: d for d in result.detectors}
    assert by_name["isolation_forest"].ran is False
    assert by_name["local_outlier"].ran is False
    assert any("skipped" in w for w in result.warnings)
    assert np.isfinite(result.scores).all()


def test_robust_z_scores_handles_empty_numeric():
    df = pd.DataFrame({"label": ["a", "b", "c"]})
    z = robust_z_scores(df)
    assert len(z) == 3
    assert np.isfinite(z).all()
