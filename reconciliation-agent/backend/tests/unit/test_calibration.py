import pytest

from core.matching.calibration import (
    ConfidenceCalibrator,
    expected_calibration_error,
    reliability_diagram,
)


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        ConfidenceCalibrator().predict(0.5)


def test_fit_requires_matching_lengths():
    with pytest.raises(ValueError):
        ConfidenceCalibrator().fit([0.1, 0.2], [1.0])


def test_fit_requires_at_least_one_example():
    with pytest.raises(ValueError):
        ConfidenceCalibrator().fit([], [])


def test_isotonic_fit_is_monotonic_non_decreasing():
    cal = ConfidenceCalibrator()
    raw = [0.1, 0.3, 0.5, 0.7, 0.9]
    labels = [0.0, 0.0, 1.0, 1.0, 1.0]
    cal.fit(raw, labels)
    predictions = [cal.predict(x) for x in raw]
    assert predictions == sorted(predictions)


def test_perfectly_calibrated_predictions_have_zero_ece():
    # Every prediction in the 0.9 bin is right 90% of the time -> mean
    # predicted probability equals observed frequency exactly.
    predictions = [0.9] * 10
    labels = [1.0] * 9 + [0.0]
    ece = expected_calibration_error(predictions, labels, predictions, n_bins=10)
    assert ece == pytest.approx(0.0, abs=1e-6)


def test_overconfident_predictions_have_positive_ece():
    predictions = [0.95, 0.95, 0.95, 0.95]
    labels = [1.0, 0.0, 0.0, 0.0]
    ece = expected_calibration_error(predictions, labels, predictions, n_bins=10)
    assert ece > 0.5


def test_reliability_diagram_groups_into_bins():
    predictions = [0.05, 0.15, 0.85, 0.95]
    labels = [1.0, 0.0, 1.0, 1.0]
    bins = reliability_diagram(predictions, labels, n_bins=10)
    assert sum(b.count for b in bins) == 4
    assert all(0.0 <= b.mean_predicted <= 1.0 for b in bins)
