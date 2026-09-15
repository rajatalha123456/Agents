import json
from copy import deepcopy

import pytest
from fastapi import HTTPException

from app import preprocessing as prep
from app.routers import generic_anomaly as detector


def prepare(rows, **options):
    return prep.prepare(rows, detector._profile_columns, prep.Policy(**options))


def bank_row(**updates):
    row = {name: "no" for name in prep.BANK_COLUMNS}
    row.update(age="40", job="admin.", marital="married", education="university.degree",
               contact="cellular", month="may", day_of_week="mon", duration="100", campaign="1",
               pdays="999", previous="0", poutcome="nonexistent")
    for name in prep.BANK_CONTEXT:
        row[name] = "1.1"
    row.update(updates)
    return row


def test_normalization_preserves_source_ids_rows_and_extreme_values():
    rows = [{" account_id ": "001", " amount ": " PKR 1,200.00 ", "status": "unknown", "date": "2026/09/05"},
            {" account_id ": "001", " amount ": "1300", "status": " approved ", "date": "2026-09-06"},
            {" account_id ": "002", " amount ": "999999999", "status": "approved", "date": "2026-09-07"}]
    original = deepcopy(rows)
    result = prepare(rows)
    assert rows == original
    assert result.rows[0] == {"account_id": "001", "amount": 1200.0, "status": None, "date": "2026-09-05"}
    assert result.source_rows[0]["amount"] == " PKR 1,200.00 "
    assert result.rows[2]["amount"] == 999999999
    assert result.profiles["account_id"]["type"] == "identifier"
    assert result.profiles["account_id"]["model_eligible"] is False
    assert result.report["input_rows"] == result.report["output_rows"] == 3
    assert result.report["counts"]["missing_token"] == 1
    assert result.report["imputed_cells"] == 0


def test_invalid_values_are_quality_findings_without_numeric_imputation():
    rows = [{"amount": value, "date": "2026-09-05"} for value in ["10", "11", "12", "13", "1,2"]]
    rows[-1]["date"] = "2026-02-31"
    result = detector.analyze_rows(rows, call_ai=False)
    assert result["prepared_preview_rows"][-1]["values"]["amount"] is None
    assert result["prepared_preview_rows"][-1]["values"]["date"] is None
    assert result["preview_rows"][-1]["values"]["amount"] == "1,2"
    assert result["preprocessing"]["counts"]["invalid"] == 2
    assert len([a for a in result["anomalies"] if a["type"] == "type_mismatch"]) == 2
    assert result["summary"]["data_quality_score"] == 80


def test_mixed_units_and_targets_are_excluded():
    result = prepare([{"amount": "USD 100", "rate": "5%", "target": "yes"},
                      {"amount": "PKR 200", "rate": ".05", "target": "no"}])
    for name in ("amount", "rate", "target"):
        assert not result.profiles[name]["model_eligible"]
    assert result.profiles["amount"]["role"] == "excluded"
    assert result.profiles["target"]["role"] == "target"
    assert result.rows[0]["rate"] == "5%"


def test_header_collision_and_nonobject_json_fail_without_dropping_records():
    with pytest.raises(ValueError, match="collide"):
        prepare([{"amount": 1, " amount ": 2}])
    with pytest.raises(HTTPException) as error:
        detector._json_rows([{"amount": 1}, 2])
    assert error.value.status_code == 400


def test_bank_dictionary_handles_unknown_sentinel_context_and_target():
    rows = [bank_row(default="unknown"), bank_row(pdays="3", previous="1", duration="120")]
    result = prepare(rows)
    assert result.report["profile"] == "bank_marketing"
    assert result.rows[0]["default"] is None
    assert result.rows[0]["pdays"] is None
    assert result.profiles["pdays"]["not_applicable"] == 1
    assert result.profiles["pdays"]["missing"] == 0
    assert result.profiles["default"]["missing"] == 1
    assert result.rows[1]["pdays"] == 3
    assert result.source_rows[0]["pdays"] == "999"
    for name in ["y", *prep.BANK_CONTEXT]:
        assert not result.profiles[name]["model_eligible"]
    report = detector.analyze_rows(rows, call_ai=False)
    assert not any(a["type"] == "missing_values" and a["column"] == "pdays" for a in report["anomalies"])
    assert report["summary"]["data_quality_score"] == round(100 * 40 / 41, 2)


def test_dictionary_rules_do_not_apply_to_generic_pdays_column():
    result = prepare([{"pdays": 999}, {"pdays": 2}])
    assert result.report["profile"] == "generic"
    assert result.rows[0]["pdays"] == 999


def test_original_duplicates_and_missingness_do_not_depend_on_outlier_scores():
    rows = [{"id": 1, "amount": "10"}, {"id": 1, "amount": "10"}, {"id": 3, "amount": "10000000"}]
    report = detector.analyze_rows(rows, call_ai=False)
    assert report["preprocessing"]["duplicate_extra_rows"] == 1
    assert report["summary"]["data_quality_score"] == 100
    assert any(a["type"] == "duplicate_row" for a in report["anomalies"])


def test_ratio_checks_require_explicit_column_pairs():
    rows = [{"qty": n, "amount": n * 10} for n in range(1, 25)]
    rows[-1]["amount"] = 1
    default = detector.analyze_rows(rows, call_ai=False)
    configured = detector.analyze_rows(rows, call_ai=False, preprocessing_policy=prep.Policy(ratio_pairs=(("qty", "amount"),)))
    assert not any(a["model"] == "Ratio consistency model" for a in default["anomalies"])
    assert any(a["model"] == "Ratio consistency model" and a["row"] == 24 for a in configured["anomalies"])


def test_nonfinite_source_values_produce_json_safe_evidence():
    result = detector.analyze_rows([{"value": float('inf')}, {"value": 1}, {"value": 2}], call_ai=False)
    assert result["preprocessing"]["counts"]["invalid"] == 1
    json.dumps(result, allow_nan=False)


def test_sparse_numeric_feature_is_not_required_by_knn():
    result = prepare([{"amount": n, "sparse": n if n < 2 else None} for n in range(10)])
    assert result.profiles["sparse"]["model_eligible"]
    assert not result.profiles["sparse"]["knn_eligible"]
    assert result.profiles["amount"]["knn_eligible"]
    assert result.rows[-1]["sparse"] is None


def test_temporal_context_is_not_categorical_rarity_evidence():
    rows = [{"Date": f"{i:02d}-01-09", "Candel Time": "4:00", "AM/PM": "PM", "amount": i}
            for i in range(1, 25)]
    result = prepare(rows)
    for name in ("Date", "Candel Time", "AM/PM"):
        assert result.profiles[name]["model_eligible"] is False
    report = detector.analyze_rows(rows, call_ai=False, include_all=True)
    assert not any(a["type"] in {"rare_category", "rare_combination"} for a in report["anomalies"])


def test_fractional_risk_bands_account_for_every_row():
    findings = [{"score": score} for score in [34.9, 54.9, 64.9, 84.9, 100]]
    bands = detector._risk_distribution(findings, 10)
    assert sum(b["count"] for b in bands) == 10
    assert [b["count"] for b in bands] == [6, 1, 1, 1, 1]


def test_review_priority_does_not_add_repeated_detector_signals():
    rows = [{"a": i % 17, "b": (i % 17) * 2, "c": (i % 17) * 3} for i in range(100)]
    rows.append({"a": 1000, "b": 2000, "c": 3000})
    report = detector.analyze_rows(rows, call_ai=False, include_all=True)
    for finding in report["anomalies"]:
        if finding["layer"] == "L4":
            evidence = [a["score"] for a in report["anomalies"] if a["row"] == finding["row"] and a["layer"] != "L4"]
            assert finding["score"] == max(evidence)
