import pandas as pd
import pytest

from sampling.determinism import (
    canonical_order,
    dataset_fingerprint,
    derive_seed,
    make_rng,
    round_amounts,
    library_versions,
)


def _frame(ids, amounts):
    return pd.DataFrame({"item_id": ids, "amount": amounts})


def test_canonical_order_identical_for_shuffled_input():
    f1 = _frame(["c", "a", "b"], [3, 1, 2])
    f2 = _frame(["a", "b", "c"], [1, 2, 3])
    o1 = canonical_order(f1, "item_id")
    o2 = canonical_order(f2, "item_id")
    assert list(o1["item_id"]) == list(o2["item_id"]) == ["a", "b", "c"]


def test_canonical_order_raises_on_null_id():
    f = _frame(["a", None, "c"], [1, 2, 3])
    with pytest.raises(ValueError):
        canonical_order(f, "item_id")


def test_canonical_order_raises_on_duplicate_ids():
    f = _frame(["a", "a", "b"], [1, 2, 3])
    with pytest.raises(ValueError):
        canonical_order(f, "item_id")


def test_fingerprint_stable_across_row_order():
    f1 = _frame(["a", "b", "c"], [1.0, 2.0, 3.0])
    f2 = _frame(["c", "a", "b"], [3.0, 1.0, 2.0])
    assert dataset_fingerprint(f1, "item_id", "amount") == dataset_fingerprint(f2, "item_id", "amount")


def test_fingerprint_changes_on_amount_change():
    f1 = _frame(["a", "b"], [1.00, 2.00])
    f2 = _frame(["a", "b"], [1.01, 2.00])
    assert dataset_fingerprint(f1, "item_id", "amount") != dataset_fingerprint(f2, "item_id", "amount")


def test_round_amounts():
    s = pd.Series([1.005, 2.004, 3.0])
    rounded = round_amounts(s)
    assert list(rounded) == [1.0, 2.0, 3.0] or list(rounded) == [1.01, 2.0, 3.0]


def test_derive_seed_different_strata_differ():
    s1 = derive_seed("fp", "v1", "mus")
    s2 = derive_seed("fp", "v1", "random_control")
    assert s1 != s2


def test_derive_seed_same_stratum_same_seed():
    s1 = derive_seed("fp", "v1", "mus", "seedA")
    s2 = derive_seed("fp", "v1", "mus", "seedA")
    assert s1 == s2


def test_derive_seed_changes_with_user_seed():
    s1 = derive_seed("fp", "v1", "mus", "seedA")
    s2 = derive_seed("fp", "v1", "mus", "seedB")
    assert s1 != s2


def test_make_rng_reproducible():
    rng1 = make_rng(42)
    rng2 = make_rng(42)
    assert list(rng1.uniform(size=5)) == list(rng2.uniform(size=5))


def test_library_versions_has_expected_keys():
    v = library_versions()
    for key in ("python", "numpy", "pandas", "scipy", "scikit-learn"):
        assert key in v
