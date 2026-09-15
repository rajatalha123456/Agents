"""Benchmark whether risk scores beat random ranking against confirmed labels.

This module decides whether the product's ranking can be sold as better
than random. Intervals are reported, never a bare point estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
BEATS_RANDOM = "BEATS_RANDOM"
WORSE_THAN_RANDOM = "WORSE_THAN_RANDOM"
NOT_DISTINGUISHABLE_FROM_RANDOM = "NOT_DISTINGUISHABLE_FROM_RANDOM"


def _top_k_mask(scores: np.ndarray, k: int) -> np.ndarray:
    n = len(scores)
    order = np.lexsort((np.arange(n), -scores))
    mask = np.zeros(n, dtype=bool)
    mask[order[:k]] = True
    return mask


def precision_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> float:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if k <= 0:
        return 0.0
    k = min(k, len(scores))
    mask = _top_k_mask(scores, k)
    return float(labels[mask].sum() / k)


def recall_at_k(scores: np.ndarray, labels: np.ndarray, k: int) -> float:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=float)
    total_positive = labels.sum()
    if total_positive <= 0:
        return 0.0
    k = min(k, len(scores))
    mask = _top_k_mask(scores, k)
    return float(labels[mask].sum() / total_positive)


@dataclass(frozen=True)
class BenchmarkResult:
    k: int
    n: int
    findings_total: int
    base_rate: float
    precision: float
    recall: float
    lift: float
    lift_ci_low: float
    lift_ci_high: float
    verdict: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def statement(self) -> str:
        captured = round(self.recall * self.findings_total)
        return (
            f"Captured {captured} of {self.findings_total} findings in the "
            f"top {self.k} ({self.recall * 100:.1f}% recall, "
            f"{self.precision * 100:.1f}% precision), "
            f"{self.lift:.2f}x the random baseline "
            f"(95% CI [{self.lift_ci_low:.2f}, {self.lift_ci_high:.2f}]). "
            f"Verdict: {self.verdict}."
        )


def benchmark_ranking(
    scores: np.ndarray,
    labels: np.ndarray,
    k: int | None = None,
    k_fraction: float = 0.10,
    bootstrap_iterations: int = 2000,
    seed: int = 0,
    min_findings: int = 30,
) -> BenchmarkResult:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(scores)
    if len(labels) != n:
        raise ValueError("scores and labels must have the same length")

    if k is None:
        k = max(1, int(round(n * k_fraction)))
    k = min(k, n)

    findings_total = int(labels.sum())
    base_rate = findings_total / n if n else 0.0

    warnings: list[str] = []
    if base_rate > 0.5:
        warnings.append(
            "base rate exceeds 50%; lift is a weak signal here -- report "
            "precision and recall directly."
        )

    precision = precision_at_k(scores, labels, k)
    recall = recall_at_k(scores, labels, k)
    lift = precision / base_rate if base_rate > 0 else float("inf")

    rng = np.random.Generator(np.random.PCG64(seed))
    lifts = np.empty(bootstrap_iterations)
    for i in range(bootstrap_iterations):
        idx = rng.integers(0, n, size=n)
        b_scores = scores[idx]
        b_labels = labels[idx]
        b_base_rate = b_labels.sum() / n if n else 0.0
        b_precision = precision_at_k(b_scores, b_labels, k)
        lifts[i] = b_precision / b_base_rate if b_base_rate > 0 else np.nan

    valid_lifts = lifts[np.isfinite(lifts)]
    if valid_lifts.size >= bootstrap_iterations * 0.5:
        ci_low = float(np.percentile(valid_lifts, 2.5))
        ci_high = float(np.percentile(valid_lifts, 97.5))
        ci_usable = True
    else:
        ci_low, ci_high = float("nan"), float("nan")
        ci_usable = False

    if findings_total < min_findings or not ci_usable:
        verdict = INSUFFICIENT_DATA
        warnings.append(
            f"only {findings_total} confirmed finding(s) (minimum "
            f"{min_findings} required) or the bootstrap confidence interval "
            "could not be computed reliably; INSUFFICIENT_DATA wins "
            "regardless of the point lift."
        )
    elif ci_low > 1.0:
        verdict = BEATS_RANDOM
    elif ci_high < 1.0:
        verdict = WORSE_THAN_RANDOM
        warnings.append(
            "ranking performs worse than random -- check for inverted "
            "scoring or label leakage."
        )
    else:
        verdict = NOT_DISTINGUISHABLE_FROM_RANDOM

    return BenchmarkResult(
        k=k,
        n=n,
        findings_total=findings_total,
        base_rate=base_rate,
        precision=precision,
        recall=recall,
        lift=lift,
        lift_ci_low=ci_low,
        lift_ci_high=ci_high,
        verdict=verdict,
        warnings=tuple(warnings),
    )
