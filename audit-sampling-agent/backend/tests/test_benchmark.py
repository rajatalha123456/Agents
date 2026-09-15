import numpy as np
import pytest

from sampling.benchmark import (
    benchmark_ranking,
    precision_at_k,
    recall_at_k,
    BEATS_RANDOM,
    WORSE_THAN_RANDOM,
    NOT_DISTINGUISHABLE_FROM_RANDOM,
    INSUFFICIENT_DATA,
)


def _strong_signal(n=1000, seed=0):
    rng = np.random.default_rng(seed)
    labels = np.zeros(n)
    positive_idx = rng.choice(n, size=100, replace=False)
    labels[positive_idx] = 1
    scores = rng.normal(0, 1, n)
    scores[positive_idx] += 5.0  # strong separation
    return scores, labels


def _pure_noise(n=1000, seed=0):
    rng = np.random.default_rng(seed)
    labels = np.zeros(n)
    positive_idx = rng.choice(n, size=100, replace=False)
    labels[positive_idx] = 1
    scores = rng.normal(0, 1, n)
    return scores, labels


def test_strong_ranking_gives_beats_random():
    scores, labels = _strong_signal()
    r = benchmark_ranking(scores, labels, k_fraction=0.10, bootstrap_iterations=300, seed=1)
    assert r.verdict == BEATS_RANDOM


def test_pure_noise_gives_not_distinguishable():
    scores, labels = _pure_noise()
    r = benchmark_ranking(scores, labels, k_fraction=0.10, bootstrap_iterations=300, seed=1)
    assert r.verdict == NOT_DISTINGUISHABLE_FROM_RANDOM


def test_inverted_scores_give_worse_than_random():
    scores, labels = _strong_signal()
    r = benchmark_ranking(-scores, labels, k_fraction=0.10, bootstrap_iterations=300, seed=1)
    assert r.verdict == WORSE_THAN_RANDOM


def test_few_findings_perfect_ranking_still_insufficient_data():
    n = 200
    labels = np.zeros(n)
    labels[:5] = 1
    scores = np.zeros(n)
    scores[:5] = 100  # perfect ranking, only 5 findings
    r = benchmark_ranking(scores, labels, k=10, bootstrap_iterations=200, seed=1, min_findings=30)
    assert r.verdict == INSUFFICIENT_DATA


def test_identical_seeds_give_identical_intervals():
    scores, labels = _strong_signal()
    r1 = benchmark_ranking(scores, labels, bootstrap_iterations=300, seed=7)
    r2 = benchmark_ranking(scores, labels, bootstrap_iterations=300, seed=7)
    assert r1.lift_ci_low == r2.lift_ci_low
    assert r1.lift_ci_high == r2.lift_ci_high


def test_precision_recall_at_k_basic():
    scores = np.array([5, 4, 3, 2, 1])
    labels = np.array([1, 1, 0, 0, 0])
    assert precision_at_k(scores, labels, 2) == 1.0
    assert recall_at_k(scores, labels, 2) == 1.0


def test_statement_contains_verdict():
    scores, labels = _strong_signal()
    r = benchmark_ranking(scores, labels, bootstrap_iterations=200, seed=1)
    assert r.verdict in r.statement()
