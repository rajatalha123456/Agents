"""ISA 530 / AU-C 530 sample size determination.

Pure functions, no I/O, no database, no HTTP. This module is covered by
the Phase 0 test suite and must remain importable without any
infrastructure dependency.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from scipy import stats

# ---------------------------------------------------------------------------
# Reliability factor (Poisson upper confidence bound)
# ---------------------------------------------------------------------------

def reliability_factor(overstatements: int, confidence_level: float) -> float:
    """Poisson-based reliability factor RF(k, c) = 0.5 * chi2.ppf(c, 2k+2).

    This is the actual mathematical basis for the published AICPA/ISA 530
    reliability factor tables, computed directly so that any confidence
    level is supported and the result stays auditable back to a formula.
    """
    if overstatements < 0:
        raise ValueError("overstatements must be >= 0")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be in (0, 1)")
    return 0.5 * stats.chi2.ppf(confidence_level, 2 * overstatements + 2)


# ---------------------------------------------------------------------------
# Expansion factor (empirical AICPA table, linearly interpolated)
# ---------------------------------------------------------------------------

_EXPANSION_TABLE = (
    (0.50, 1.00),
    (0.75, 1.25),
    (0.80, 1.30),
    (0.85, 1.40),
    (0.90, 1.50),
    (0.95, 1.60),
    (0.99, 1.90),
)


def expansion_factor(confidence_level: float) -> float:
    """Empirical AICPA expansion factor, linearly interpolated between
    tabulated confidence levels. Clamped (not extrapolated) outside the
    tabulated range [0.50, 0.99].
    """
    if confidence_level <= _EXPANSION_TABLE[0][0]:
        return _EXPANSION_TABLE[0][1]
    if confidence_level >= _EXPANSION_TABLE[-1][0]:
        return _EXPANSION_TABLE[-1][1]
    for (c0, e0), (c1, e1) in zip(_EXPANSION_TABLE, _EXPANSION_TABLE[1:]):
        if c0 <= confidence_level <= c1:
            frac = (confidence_level - c0) / (c1 - c0)
            return e0 + frac * (e1 - e0)
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# Sample size results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SampleSizeResult:
    sample_size: int
    sampling_interval: float
    book_value: float
    tolerable_misstatement: float
    expected_misstatement: float
    confidence_level: float
    reliability_factor: float
    expansion_factor: float
    adjusted_tolerable: float
    basis: str

    def as_workpaper(self) -> dict:
        d = asdict(self)
        for key in (
            "sampling_interval", "book_value", "tolerable_misstatement",
            "expected_misstatement", "adjusted_tolerable",
        ):
            d[key] = round(d[key], 2)
        d["reliability_factor"] = round(d["reliability_factor"], 4)
        d["expansion_factor"] = round(d["expansion_factor"], 4)
        return d


def mus_interval(book_value: float, sample_size: int) -> float:
    if sample_size <= 0:
        raise ValueError("sample_size must be > 0")
    return book_value / sample_size


def mus_sample_size(
    book_value: float,
    tolerable_misstatement: float,
    expected_misstatement: float = 0.0,
    confidence_level: float = 0.95,
    min_sample_size: int = 0,
    max_sample_size: int | None = None,
) -> SampleSizeResult:
    if book_value < 0:
        raise ValueError("book_value must be >= 0")
    if tolerable_misstatement <= 0:
        raise ValueError("tolerable_misstatement must be > 0")

    rf0 = reliability_factor(0, confidence_level)
    ef = expansion_factor(confidence_level)
    adjusted = tolerable_misstatement - expected_misstatement * ef

    if adjusted <= 0:
        raise ValueError(
            "MUS cannot produce a meaningful sample: expected misstatement "
            "expanded by the expansion factor meets or exceeds tolerable "
            "misstatement. Reconsider materiality, test 100% of the "
            "population, or use classical variables sampling."
        )

    n = math.ceil(book_value * rf0 / adjusted)
    basis = (
        f"n = ceil(book_value[{book_value}] * RF(0,{confidence_level})[{rf0:.4f}] "
        f"/ adjusted_tolerable[{adjusted:.2f}])"
    )

    if n < min_sample_size:
        n = min_sample_size
        basis += f"; raised to min_sample_size={min_sample_size}"

    if max_sample_size is not None and n > max_sample_size:
        n = max_sample_size
        basis += (
            f"; CAPPED at max_sample_size={max_sample_size} "
            "-- achieved assurance is lower than the stated confidence level"
        )

    interval = mus_interval(book_value, n)

    return SampleSizeResult(
        sample_size=n,
        sampling_interval=interval,
        book_value=book_value,
        tolerable_misstatement=tolerable_misstatement,
        expected_misstatement=expected_misstatement,
        confidence_level=confidence_level,
        reliability_factor=rf0,
        expansion_factor=ef,
        adjusted_tolerable=adjusted,
        basis=basis,
    )


def basic_precision(confidence_level: float, sampling_interval: float) -> float:
    return reliability_factor(0, confidence_level) * sampling_interval


# ---------------------------------------------------------------------------
# Attribute sampling
# ---------------------------------------------------------------------------

def attribute_sample_size(
    tolerable_rate: float,
    expected_rate: float = 0.0,
    confidence_level: float = 0.95,
    population_size: int | None = None,
) -> int:
    if not (0.0 < tolerable_rate < 1.0):
        raise ValueError("tolerable_rate must be in (0, 1)")
    if not (0.0 <= expected_rate < tolerable_rate):
        raise ValueError("expected_rate must be in [0, tolerable_rate)")

    n = math.ceil(reliability_factor(0, confidence_level) / tolerable_rate)
    while True:
        k = math.floor(expected_rate * n)
        n_new = math.ceil(reliability_factor(k, confidence_level) / tolerable_rate)
        if n_new == n:
            break
        n = n_new

    if population_size is not None and population_size > 0:
        n = min(n, population_size)

    return n
