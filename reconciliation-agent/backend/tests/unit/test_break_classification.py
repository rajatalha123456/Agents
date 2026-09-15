import pytest

from core.breaks.classification import (
    BreakTypeInfo,
    BreakTypeRegistry,
    UnknownBreakType,
    isolating_dimensions_match,
)


def registry():
    return BreakTypeRegistry([
        BreakTypeInfo(code="AMT-02", family="AMT", risk_weight=6, is_sensitive=False),
        BreakTypeInfo(code="TIM-05", family="TIM", risk_weight=8, is_sensitive=True),
    ])


def test_lookup_returns_registered_entry():
    entry = registry().get("AMT-02")
    assert entry.risk_weight == 6
    assert entry.is_sensitive is False


def test_unknown_code_raises():
    with pytest.raises(UnknownBreakType):
        registry().get("XXX-99")


def test_duplicate_code_rejected_at_construction():
    with pytest.raises(ValueError):
        BreakTypeRegistry([
            BreakTypeInfo(code="AMT-02", family="AMT", risk_weight=1, is_sensitive=False),
            BreakTypeInfo(code="AMT-02", family="AMT", risk_weight=2, is_sensitive=False),
        ])


def test_is_sensitive_helper():
    r = registry()
    assert r.is_sensitive("TIM-05") is True
    assert r.is_sensitive("AMT-02") is False


def test_isolating_dimensions_must_match():
    assert isolating_dimensions_match({"pool_id": "p1"}, {"pool_id": "p1"}, ["pool_id"]) is True
    assert isolating_dimensions_match({"pool_id": "p1"}, {"pool_id": "p2"}, ["pool_id"]) is False


def test_isolating_dimensions_both_missing_is_fine():
    assert isolating_dimensions_match({}, {}, ["pool_id"]) is True


def test_non_isolating_keys_ignored():
    assert isolating_dimensions_match({"note": "a"}, {"note": "b"}, []) is True
