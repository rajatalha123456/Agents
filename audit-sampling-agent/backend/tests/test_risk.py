import numpy as np
import pytest

from sampling.risk import RiskWeights, aggregate_risk


def test_all_components_at_80_yields_80_even_with_one_absent():
    weights = RiskWeights()
    scores = np.array([80.0, 80.0, 80.0])
    r = aggregate_risk(weights, anomaly=scores, rules=scores, history=scores, data_quality=scores)
    assert np.allclose(r.scores, 80.0)


def test_without_labels_excludes_supervised():
    w = RiskWeights.without_labels()
    assert w.supervised == 0.0


def test_unvalidated_warns():
    weights = RiskWeights()
    r = aggregate_risk(weights, anomaly=np.array([50.0]))
    assert any("UNVALIDATED" in w for w in r.warnings)


def test_out_of_range_raises():
    weights = RiskWeights()
    with pytest.raises(ValueError):
        aggregate_risk(weights, anomaly=np.array([150.0, 50.0]))


def test_zero_to_one_scale_raises():
    weights = RiskWeights()
    with pytest.raises(ValueError):
        aggregate_risk(weights, anomaly=np.array([0.1, 0.5, 0.9]))


def test_mismatched_lengths_raise():
    weights = RiskWeights()
    with pytest.raises(ValueError):
        aggregate_risk(weights, anomaly=np.array([50.0, 60.0]), rules=np.array([50.0]))


def test_absent_components_redistribute_not_zero():
    weights = RiskWeights.without_labels()
    scores = np.array([100.0, 100.0])
    r = aggregate_risk(weights, anomaly=scores, rules=scores)
    assert np.allclose(r.scores, 100.0)
    assert any("redistributed" in w for w in r.warnings)


def test_constant_value_component_allowed_even_if_le_1():
    weights = RiskWeights()
    r = aggregate_risk(weights, anomaly=np.array([0.0, 0.0, 0.0]))
    assert np.allclose(r.scores, 0.0)
