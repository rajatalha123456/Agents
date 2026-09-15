"""§9.1 — confidence calibration. A raw L4/L5 similarity score is not a
probability; isotonic regression fit per universe on historical labelled
dispositions turns it into one. Re-fit monthly per the plan; this module
only owns the fit/predict/reliability-diagram mechanics, not the schedule.
"""
from __future__ import annotations

from dataclasses import dataclass

from sklearn.isotonic import IsotonicRegression


@dataclass(frozen=True)
class ReliabilityBin:
    bin_lower: float
    bin_upper: float
    mean_predicted: float
    observed_frequency: float
    count: int


class ConfidenceCalibrator:
    """Wraps a per-universe isotonic fit. `raw_scores` are L4/L5 output in
    [0, 1]; `labels` are 1.0 for a confirmed-correct match, 0.0 for a
    confirmed-false one, both from historical human/assurance dispositions
    (§9.4) — never from unreviewed auto-matches, or the model calibrates
    against its own errors.
    """

    def __init__(self) -> None:
        self._model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._fitted = False

    def fit(self, raw_scores: list[float], labels: list[float]) -> None:
        if len(raw_scores) != len(labels):
            raise ValueError("raw_scores and labels must be the same length")
        if not raw_scores:
            raise ValueError("cannot fit calibration on zero examples")
        self._model.fit(raw_scores, labels)
        self._fitted = True

    def predict(self, raw_score: float) -> float:
        if not self._fitted:
            raise RuntimeError("calibrator has not been fit yet")
        return float(self._model.predict([raw_score])[0])


def expected_calibration_error(raw_scores: list[float], labels: list[float], predictions: list[float], n_bins: int = 10) -> float:
    """§9.3 ECE target (<= 0.05, breach suspends auto-match). Standard
    equal-width-bin ECE: weighted mean absolute gap between each bin's
    average predicted probability and its actual observed frequency.
    """
    if not (len(raw_scores) == len(labels) == len(predictions)):
        raise ValueError("raw_scores, labels and predictions must be the same length")
    if not predictions:
        return 0.0

    bins: list[list[int]] = [[] for _ in range(n_bins)]
    for idx, p in enumerate(predictions):
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append(idx)

    total = len(predictions)
    ece = 0.0
    for indices in bins:
        if not indices:
            continue
        mean_pred = sum(predictions[i] for i in indices) / len(indices)
        observed = sum(labels[i] for i in indices) / len(indices)
        ece += (len(indices) / total) * abs(mean_pred - observed)
    return ece


def reliability_diagram(predictions: list[float], labels: list[float], n_bins: int = 10) -> list[ReliabilityBin]:
    """§21.5 — the "when the agent says 90%, how often is it right?" chart data."""
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must be the same length")

    bins: list[list[int]] = [[] for _ in range(n_bins)]
    for idx, p in enumerate(predictions):
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append(idx)

    width = 1.0 / n_bins
    result = []
    for i, indices in enumerate(bins):
        if not indices:
            continue
        mean_pred = sum(predictions[j] for j in indices) / len(indices)
        observed = sum(labels[j] for j in indices) / len(indices)
        result.append(ReliabilityBin(
            bin_lower=i * width, bin_upper=(i + 1) * width,
            mean_predicted=mean_pred, observed_frequency=observed, count=len(indices),
        ))
    return result
