import pytest

from sampling.statistics import (
    reliability_factor,
    expansion_factor,
    mus_sample_size,
    mus_interval,
    attribute_sample_size,
    basic_precision,
)

# Published AICPA/ISA 530 tables carry small historical rounding baked in
# from pre-computer-era derivation; the exact Poisson formula the spec
# mandates can legitimately differ by 0.01 from the published figure. We
# assert against the formula's own precision with a small tolerance rather
# than blind equality to the rounded table.
PUBLISHED_RF = [
    (0, 0.95, 3.00), (1, 0.95, 4.75), (2, 0.95, 6.30), (3, 0.95, 7.76),
    (0, 0.99, 4.61), (1, 0.99, 6.64),
    (0, 0.90, 2.31), (0, 0.85, 1.90), (0, 0.80, 1.61),
]


@pytest.mark.parametrize("k,c,expected", PUBLISHED_RF)
def test_reliability_factor_matches_published_tables(k, c, expected):
    assert reliability_factor(k, c) == pytest.approx(expected, abs=0.011)


def test_reliability_factor_rejects_negative_k():
    with pytest.raises(ValueError):
        reliability_factor(-1, 0.95)


def test_reliability_factor_rejects_bad_confidence():
    with pytest.raises(ValueError):
        reliability_factor(0, 1.5)


def test_expansion_factor_table_points():
    assert expansion_factor(0.95) == pytest.approx(1.60)
    assert expansion_factor(0.90) == pytest.approx(1.50)
    assert expansion_factor(0.99) == pytest.approx(1.90)


def test_expansion_factor_interpolates():
    v = expansion_factor(0.775)  # midpoint of 0.75->1.25 and 0.80->1.30
    assert v == pytest.approx(1.275, abs=1e-6)


def test_expansion_factor_clamps_outside_range():
    assert expansion_factor(0.10) == expansion_factor(0.50)
    assert expansion_factor(0.999) == expansion_factor(0.99)


def test_mus_sample_size_basic():
    r = mus_sample_size(1_000_000, 50_000, 0, 0.95)
    assert r.sample_size == 60
    assert r.sampling_interval == pytest.approx(1_000_000 / 60)


def test_mus_sample_size_with_expected_misstatement():
    r = mus_sample_size(1_000_000, 50_000, 10_000, 0.95)
    assert r.adjusted_tolerable == pytest.approx(34_000, abs=1)
    assert r.sample_size == 89


def test_mus_sample_size_raises_when_adjusted_non_positive():
    with pytest.raises(ValueError):
        mus_sample_size(1_000_000, 50_000, 35_000, 0.95)


def test_mus_sample_size_cap_is_flagged():
    r = mus_sample_size(1_000_000, 50_000, 0, 0.95, max_sample_size=10)
    assert r.sample_size == 10
    assert "CAPPED" in r.basis


def test_mus_sample_size_min_floor():
    r = mus_sample_size(100, 90, 0, 0.80, min_sample_size=25)
    assert r.sample_size >= 25


def test_mus_interval():
    assert mus_interval(1000, 10) == 100


def test_basic_precision():
    bp = basic_precision(0.95, 1000)
    assert bp == pytest.approx(reliability_factor(0, 0.95) * 1000)


def test_attribute_sample_size_published():
    assert attribute_sample_size(0.05, 0.0, 0.95) == 60


def test_attribute_sample_size_capped_by_population():
    n = attribute_sample_size(0.05, 0.0, 0.95, population_size=10)
    assert n == 10


def test_sample_size_result_as_workpaper_rounds():
    r = mus_sample_size(1_000_000.123, 50_000, 0, 0.95)
    wp = r.as_workpaper()
    assert wp["book_value"] == round(1_000_000.123, 2)
    assert isinstance(wp["sample_size"], int)
