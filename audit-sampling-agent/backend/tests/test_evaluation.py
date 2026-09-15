import pytest

from sampling.evaluation import TestedItem, project_misstatement
from sampling.selection import SelectionBasis
from sampling.statistics import reliability_factor

INTERVAL = 10_000
CONF = 0.95


def test_clean_sample_uml_equals_rf0_times_interval():
    items = [TestedItem(f"i{i}", 5000, 5000, SelectionBasis.MUS) for i in range(5)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.upper_misstatement_limit == pytest.approx(reliability_factor(0, CONF) * INTERVAL)
    assert r.conclusion == "ACCEPT"


def test_one_full_tainting_error_gives_rf1_times_interval():
    items = [TestedItem("bad", 5000, 0, SelectionBasis.MUS)] + [
        TestedItem(f"i{i}", 5000, 5000, SelectionBasis.MUS) for i in range(4)
    ]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.upper_misstatement_limit == pytest.approx(reliability_factor(1, CONF) * INTERVAL, rel=1e-6)


def test_certainty_item_known_not_projected_no_incremental_allowance():
    items = [TestedItem("big", 20_000, 15_000, SelectionBasis.MUS_CERTAINTY)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.known_misstatement == pytest.approx(5000)
    assert r.projected_misstatement == 0.0
    assert r.incremental_allowance == 0.0


def test_judgmental_items_excluded_from_projection():
    items = [TestedItem("j", 1000, 500, SelectionBasis.HIGH_RISK)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.projectable_count == 0
    assert r.judgmental_known_misstatement == pytest.approx(500)
    assert any("judgmental" in w for w in r.warnings)


def test_over_and_understatements_not_netted():
    items = [
        TestedItem("over", 5000, 4000, SelectionBasis.MUS),   # overstated by 1000
        TestedItem("under", 5000, 6000, SelectionBasis.MUS),  # understated by 1000
    ]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.projected_misstatement > 0
    assert r.projected_understatement > 0
    assert any("understatement" in w.lower() for w in r.warnings)


def test_reject_when_mlm_exceeds_tolerable():
    items = [TestedItem(f"i{i}", 5000, 0, SelectionBasis.MUS) for i in range(20)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=1000)
    assert r.conclusion == "REJECT"


def test_no_projectable_items_yields_inconclusive_no_conclusion():
    items = [TestedItem("j", 1000, 900, SelectionBasis.AUDITOR_MANUAL)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    assert r.projectable_count == 0
    assert r.conclusion == "INCONCLUSIVE"


def test_tested_item_not_collected_as_pytest_test():
    # TestedItem.__test__ = False must prevent pytest collection warnings;
    # this test simply confirms the attribute is set.
    assert TestedItem.__test__ is False


def test_as_workpaper_rounds_and_contains_expected_keys():
    items = [TestedItem("i", 5000, 5000, SelectionBasis.MUS)]
    r = project_misstatement(items, INTERVAL, CONF, tolerable_misstatement=100_000)
    wp = r.as_workpaper()
    for key in (
        "known_misstatement", "projected_misstatement", "most_likely_misstatement",
        "basic_precision", "incremental_allowance", "allowance_for_sampling_risk",
        "upper_misstatement_limit", "tolerable_misstatement", "projected_understatement",
        "judgmental_known_misstatement", "conclusion", "conclusion_basis", "warnings",
    ):
        assert key in wp
