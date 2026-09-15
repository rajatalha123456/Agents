from app.routers import generic_anomaly


def _stub_report(result):
    return {
        "provider": "test",
        "model": "stub",
        "status": "generated",
        "text": "Stubbed analyst report.",
    }


def test_generic_detector_excludes_identifier_and_returns_visual_evidence(monkeypatch):
    monkeypatch.setattr(generic_anomaly, "_call_gemini_report", _stub_report)
    rows = [
        {"id": str(index), "qty": str(index), "amount": str(index * 10), "region": "North", "status": "approved"}
        for index in range(1, 23)
    ]
    rows.extend([
        {"id": "23", "qty": "23", "amount": "7", "region": "North", "status": "approved"},
        {"id": "24", "qty": "24", "amount": "240", "region": "South", "status": "approved"},
        {"id": "25", "qty": "25", "amount": "", "region": "North", "status": "manual_review"},
        {"id": "25", "qty": "25", "amount": "", "region": "North", "status": "manual_review"},
    ])

    from app.preprocessing import Policy
    result = generic_anomaly.analyze_rows(rows, preprocessing_policy=Policy(ratio_pairs=(("qty", "amount"),)))

    assert next(column for column in result["columns"] if column["name"] == "id")["type"] == "identifier"
    assert result["summary"]["total_anomalies"] > 0
    assert len(result["score_points"]) == result["row_count"]
    assert result["driver_breakdown"]
    assert result["model_card"]["model_count"] == len(result["model_inventory"])
    assert result["model_card"]["active_model_count"] > 0
    assert any(model["family"] == "unsupervised ML model" for model in result["model_inventory"])
    assert "23" in result["row_snapshots"]
    assert result["row_snapshots"]["23"]["values"]["amount"] == "7"
    assert any(item["layer"] == "L2" for item in result["anomalies"])
    assert any(item.get("row_values") for item in result["anomalies"] if item.get("row"))


def test_json_rows_are_flattened_and_profiled(monkeypatch):
    monkeypatch.setattr(generic_anomaly, "_call_gemini_report", _stub_report)
    rows = generic_anomaly._json_rows({
        "records": [
            {"user": {"id": "A1", "tier": "gold"}, "amount": 10},
            {"user": {"id": "A2", "tier": "gold"}, "amount": 11},
            {"user": {"id": "A3", "tier": "platinum"}, "amount": 999},
        ]
    })

    result = generic_anomaly.analyze_rows(rows)

    names = {column["name"] for column in result["columns"]}
    assert {"user.id", "user.tier", "amount"}.issubset(names)
    assert result["preview_rows"][0]["values"]["user.tier"] == "gold"
    assert result["ai_report"]["provider"] == "test"


def test_generic_api_persists_history_and_explains_selected_anomaly(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(generic_anomaly, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(generic_anomaly, "_call_gemini_report", _stub_report)
    monkeypatch.setattr(generic_anomaly, "_call_gemini", lambda prompt, max_tokens=450: {
        "provider": "test",
        "model": "stub",
        "status": "generated",
        "text": "Selected anomaly explained from model evidence.",
    })

    csv_payload = "\n".join([
        "id,qty,amount,status",
        *[f"{index},{index},{index * 10},approved" for index in range(1, 23)],
        "23,23,7,approved",
        "24,24,,manual_review",
        "24,24,,manual_review",
    ])

    with TestClient(app) as client:
        response = client.post(
            "/v1/anomaly/analyze-file",
            files={"file": ("generic.csv", csv_payload, "text/csv")},
        )
        assert response.status_code == 200
        result = response.json()
        analysis_id = result["analysis_id"]
        anomaly_id = result["anomalies"][0]["id"]

        history = client.get("/v1/anomaly/analyses")
        assert history.status_code == 200
        assert any(item["analysis_id"] == analysis_id for item in history.json())

        reopened = client.get(f"/v1/anomaly/analyses/{analysis_id}")
        assert reopened.status_code == 200
        assert reopened.json()["filename"] == "generic.csv"

        explained = client.post(f"/v1/anomaly/analyses/{analysis_id}/anomalies/{anomaly_id}/explain")
        assert explained.status_code == 200
        assert explained.json()["text"] == "Selected anomaly explained from model evidence."

        chatted = client.post(
            f"/v1/anomaly/analyses/{analysis_id}/anomalies/{anomaly_id}/chat",
            json={"message": "Why was this anomaly flagged?", "history": []},
        )
        assert chatted.status_code == 200
        assert chatted.json()["text"] == "Selected anomaly explained from model evidence."


def test_panel_shaped_pairs_do_not_create_an_anomaly_for_every_row(monkeypatch):
    monkeypatch.setattr(generic_anomaly, "_call_gemini_report", _stub_report)
    rows = []
    for period in range(1, 13):
      for asset in range(1, 6):
        rows.append({
            "asset_ref": f"ASSET-{asset:03d}",
            "period": f"2026-{period:02d}",
            "income_amount": 1000 + asset * 10 + period,
            "owning_pool_id": "POOL-A",
        })
    rows[17]["income_amount"] = 4000

    result = generic_anomaly.analyze_rows(rows)

    pair_anomalies = [item for item in result["anomalies"] if item["type"] == "rare_combination"]
    assert len(pair_anomalies) == 0
    assert any(item["type"] in {"numeric_outlier", "relationship_outlier", "row_risk_explanation"} for item in result["anomalies"])


def test_row_limit_rejects_instead_of_truncating(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(generic_anomaly, "MAX_ROWS", 2)
    with pytest.raises(HTTPException) as error:
        generic_anomaly.analyze_rows([{"amount": n} for n in range(3)])
    assert error.value.status_code == 413


def test_numeric_chart_keeps_late_outliers():
    rows = [{"amount": 10 + n % 7} for n in range(6000)] + [{"amount": 100000}]
    _, profiles = generic_anomaly._profile_columns(rows)
    plot = generic_anomaly._numeric_plots(rows, profiles)[0]
    assert plot["total"] == 6001
    assert any(p["row"] == 6001 and p["outlier"] for p in plot["points"])
    assert len(plot["points"]) <= 1000


def test_statistical_box_and_histogram_count_iqr_outliers():
    records = [{"row": n + 1, "values": {"amount": value}, "flagged": False}
               for n, value in enumerate([10] * 8 + [100, None])]
    graphs = generic_anomaly._statistical_graphs(records, ["amount"])
    column = graphs["columns"][0]
    assert column["count"] == 9
    assert column["q1"] == column["median"] == column["q3"] == 10
    assert column["whisker_low"] == column["whisker_high"] == 10
    assert column["outlier_values"] == [100]
    assert column["outlier_count"] == 1
    assert sum(bin["normal"] for bin in column["histogram"]) == 8
    assert sum(bin["outliers"] for bin in column["histogram"]) == 1


def test_statistical_correlation_does_not_use_extra_flagged_evidence():
    records = [{"row": n, "values": {"x": n, "y": -2 * n, "constant": 5}, "flagged": False}
               for n in range(1, 5)]
    extra = [{"row": 99, "values": {"x": 10000, "y": 10000, "constant": 5}, "flagged": True}]
    graphs = generic_anomaly._statistical_graphs(records, ["x", "y", "constant"],
                                              scope="reservoir", total_rows=100, extra_points=extra)
    assert graphs["correlations"][0]["r"] == -1
    assert graphs["correlations"][0]["count"] == 4
    assert graphs["correlations"][1]["r"] is None
    assert graphs["columns"][0]["max"] == 4
    assert any(point["row"] == 99 for point in graphs["points"])
    assert graphs["statistics_rows"] == 4
    assert graphs["total_rows"] == 100


def test_csv_separator_detection_preserves_quoted_values():
    import io
    for separator in (",", ";", "\t", "|"):
        source = f'"age"{separator}"job"{separator}"note"\n56{separator}"admin, support"{separator}"first; second"\n'
        rows = list(generic_anomaly._csv_reader(io.StringIO(source)))
        assert rows == [{"age": "56", "job": "admin, support", "note": "first; second"}]


def test_categorical_frequencies_are_not_rebuilt_for_every_row(monkeypatch):
    calls = 0
    counter = generic_anomaly.Counter

    def count_calls(*args, **kwargs):
        nonlocal calls
        calls += 1
        return counter(*args, **kwargs)

    monkeypatch.setattr(generic_anomaly, "Counter", count_calls)
    rows = [{"status": "approved"} for _ in range(200)] + [{"status": "review"}]
    report = generic_anomaly.analyze_rows(rows, call_ai=False)
    assert calls < 30
    assert any(a["type"] == "rare_category" and a["row"] == 201 for a in report["anomalies"])


def test_synchronous_evidence_is_bounded_to_visible_findings():
    rows = [{"id": str(n), "a": "", "b": "", "c": "", "d": ""} for n in range(400)]
    report = generic_anomaly.analyze_rows(rows, call_ai=False)
    assert len(report["row_snapshots"]) <= 350
    assert report["row_count"] == 400


def test_jsonl_upload_and_limits(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(generic_anomaly, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(generic_anomaly, "_call_gemini_report", _stub_report)
    client = TestClient(app)
    response = client.post("/v1/anomaly/analyze-file", files={"file": ("rows.jsonl", '{"amount":10}\n{"amount":20}\n', "application/x-ndjson")})
    assert response.status_code == 200
    assert response.json()["row_count"] == 2
    monkeypatch.setattr(generic_anomaly, "MAX_UPLOAD_BYTES", 3)
    assert client.post("/v1/anomaly/analyze-file", files={"file": ("a.csv", "amount\n10")} ).status_code == 413
