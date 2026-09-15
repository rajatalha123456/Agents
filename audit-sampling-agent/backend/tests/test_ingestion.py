import pandas as pd
import pytest

from sampling.ingestion import ingest, profile_schema, add_risk_flags


def test_flags_added_row_count_unchanged(tmp_path):
    df = pd.DataFrame({
        "item_id": ["a", "b", "c", "a"],
        "amount": [100.0, -50.0, 0.0, 100.0],
        "timestamp": ["2024-01-01T10:00:00", "2024-01-06T02:00:00", "bad-date", "2024-01-01T10:00:00"],
        "entity": ["v1", "v2", "v1", "v1"],
    })
    flagged = add_risk_flags(df, timestamp_col="timestamp", entity_col="entity")
    assert len(flagged) == len(df)
    assert flagged["flag_negative_amount"].sum() == 1
    assert flagged["flag_zero_amount"].sum() == 1
    assert flagged["flag_duplicate_amount"].sum() == 2
    assert flagged["flag_unparseable_timestamp"].sum() == 1


def test_profile_schema_numeric_exposes_statistics_not_raw_values():
    df = pd.DataFrame({"amount": [1.0, 2.0, 3.0, 4.0, 5.0]})
    profile = profile_schema(df)
    assert "mean" in profile["amount"]
    assert "sample_values" not in profile["amount"]


def test_profile_schema_non_numeric_gives_samples_only():
    df = pd.DataFrame({"label": ["x", "y", "z"]})
    profile = profile_schema(df)
    assert "sample_values" in profile["label"]
    assert "mean" not in profile["label"]


def test_csv_round_trip(tmp_path):
    df = pd.DataFrame({"item_id": ["a", "b"], "amount": [1.5, 2.5]})
    path = tmp_path / "data.csv"
    df.to_csv(path, index=False)
    result = ingest(str(path))
    assert result.row_count == 2
    assert result.dataset_fingerprint_hex is not None


def test_profile_schema_handles_boolean_columns_without_crashing():
    # Regression: pd.api.types.is_numeric_dtype(bool_series) is True, and
    # routing bool columns into the numeric branch crashed on .quantile()
    # (numpy refuses `-` on a boolean array). Bool columns -- exactly what
    # add_risk_flags() produces -- must be profiled as categorical.
    df = pd.DataFrame({"flag_negative_amount": [True, False, False, True]})
    profile = profile_schema(df)
    assert "mean" not in profile["flag_negative_amount"]
    assert "sample_values" in profile["flag_negative_amount"]


def test_duplicate_ids_flagged_not_dropped(tmp_path):
    df = pd.DataFrame({"item_id": ["a", "a", "b"], "amount": [1.0, 2.0, 3.0]})
    path = tmp_path / "dupes.csv"
    df.to_csv(path, index=False)
    result = ingest(str(path))
    assert result.row_count == 3
    assert any("duplicate" in w for w in result.warnings)
