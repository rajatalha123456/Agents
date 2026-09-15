import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import large_data
from app.main import app
from app.routers import generic_anomaly as detector
from app.routers import uploads


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "DATA_DIR", tmp_path / "jobs")
    monkeypatch.setattr(detector, "STORAGE_DIR", tmp_path / "analyses")
    monkeypatch.setattr(uploads.shutil, "disk_usage", lambda path: SimpleNamespace(free=256 * 1024**3))
    monkeypatch.setattr(large_data, "BATCH_ROWS", 20)
    detector.ANALYSES.clear()
    return TestClient(app)


def create(client, name, data):
    response = client.post("/v1/anomaly/uploads", json={"filename": name, "size": len(data)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client, job_id, data, offset=0):
    return client.post(f"/v1/anomaly/uploads/{job_id}/chunks?offset={offset}",
                       files={"file": ("chunk", data)})


def test_45_gib_capacity_without_allocating_a_large_fixture(client, monkeypatch):
    size = 45 * 1024**3
    response = client.post("/v1/anomaly/uploads", json={"filename": "bank.csv", "size": size})
    assert response.status_code == 201
    assert response.json()["size"] == size
    monkeypatch.setattr(uploads, "MAX_FILE_BYTES", 0)
    response = client.post("/v1/anomaly/uploads", json={"filename": "bigger.csv", "size": 80 * 1024**3})
    assert response.status_code == 201
    monkeypatch.setattr(uploads.shutil, "disk_usage", lambda path: SimpleNamespace(free=size))
    assert client.post("/v1/anomaly/uploads", json={"filename": "full.csv", "size": size}).status_code == 507


def test_upload_retries_offsets_and_cancel(client):
    payload = b"amount\n10\n20\n"
    job_id = create(client, "bank.csv", payload)
    assert send(client, job_id, payload[:8]).json()["received"] == 8
    # Same bytes may be retried after a lost HTTP response, but changed bytes may not.
    assert send(client, job_id, payload[:8]).json()["received"] == 8
    assert send(client, job_id, b"different").status_code == 409
    assert send(client, job_id, b"x", 10).status_code == 409
    assert client.post(f"/v1/anomaly/uploads/{job_id}/complete").status_code == 409
    assert send(client, job_id, payload[8:], 8).status_code == 200
    assert client.get(f"/v1/anomaly/uploads/{job_id}").json()["received"] == len(payload)
    assert client.delete(f"/v1/anomaly/uploads/{job_id}").json()["state"] == "cancelled"
    assert not (uploads.job_dir(job_id) / "source").exists()


@pytest.mark.parametrize("filename", ["bank.csv", "bank.jsonl", "bank.json"])
def test_worker_scans_every_batch_and_exports_global_rows(client, filename):
    records = [{"id": n + 1, "amount": 10 + n % 6} for n in range(65)]
    records[-1]["amount"] = 100000
    if filename.endswith("csv"):
        payload = ("id,amount\n" + "\n".join(f"{r['id']},{r['amount']}" for r in records)).encode()
    elif filename.endswith("jsonl"):
        payload = "\n".join(json.dumps(r) for r in records).encode()
    else:
        payload = json.dumps({"records": records}).encode()
    job_id = create(client, filename, payload)
    assert send(client, job_id, payload).status_code == 200
    assert client.post(f"/v1/anomaly/uploads/{job_id}/complete").json()["state"] == "queued"
    # A fresh DB connection / worker sees the persisted queue.
    assert large_data.run_once()
    status = client.get(f"/v1/anomaly/uploads/{job_id}").json()
    assert status["state"] == "completed", status
    assert status["rows_done"] == 65
    report = client.get(f"/v1/anomaly/analyses/{job_id}").json()
    assert report["processing"]["batches"] == 4
    assert report["row_count"] == 65
    assert report["statistical_graphs"]["scope"] == "dataset"
    assert report["statistical_graphs"]["statistics_rows"] == 65
    assert report["statistical_graphs"]["columns"][0]["max"] == 100000
    assert sum(band["count"] for band in report["risk_distribution"]) == 65
    assert report["numeric_plots"][0]["total"] == 65
    assert any(p["row"] == 65 and p["outlier"] for p in report["numeric_plots"][0]["points"])
    exported = client.get(f"/v1/anomaly/uploads/{job_id}/findings")
    findings = [json.loads(line) for line in exported.text.splitlines()]
    assert len(findings) == report["summary"]["total_anomalies"]
    assert len({item["id"] for item in findings}) == len(findings)
    assert any(item["row"] == 65 for item in findings)
    assert not (uploads.job_dir(job_id) / "source").exists()


def test_invalid_later_record_fails_without_publishing_partial_analysis(client):
    payload = ("\n".join(json.dumps({"amount": n}) for n in range(25)) + '\n{"broken":').encode()
    job_id = create(client, "bad.jsonl", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    large_data.run_once()
    status = client.get(f"/v1/anomaly/uploads/{job_id}").json()
    assert status["state"] == "failed"
    assert status["rows_done"] == 20
    assert client.get(f"/v1/anomaly/analyses/{job_id}").status_code == 404
    assert client.get(f"/v1/anomaly/uploads/{job_id}/findings").status_code == 409
    client.delete(f"/v1/anomaly/uploads/{job_id}")
    assert not (uploads.job_dir(job_id) / "source").exists()


def test_batch_cell_limit_and_multiline_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(large_data, "BATCH_CELLS", 4)
    path = tmp_path / "source"
    path.write_text('id,note\n1,"first\nsecond"\n2,ok\n3,last\n', encoding="utf-8", newline="")
    result = list(large_data.batches(path, "bank.csv"))
    assert [len(batch) for batch in result] == [2, 1]
    assert result[0][0]["note"] == "first\nsecond"


def test_bulk_csv_accepts_semicolon_headers(tmp_path):
    path = tmp_path / "bank.csv"
    path.write_text('"age";"job"\n56;"housemaid"\n35;"admin, support"\n', encoding="utf-8")
    assert list(large_data.iter_rows(path, path.name)) == [
        {"age": "56", "job": "housemaid"}, {"age": "35", "job": "admin, support"}]


def test_worker_restart_replays_source_and_replaces_partial_findings(client):
    payload = b"amount\n10\n11\n12\n999\n"
    job_id = create(client, "restart.csv", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    large_data.update_job(job_id, state="processing", rows_done=3)
    (uploads.job_dir(job_id) / "findings.partial").write_text("old incomplete data", encoding="utf-8")
    large_data.recover_interrupted_jobs()
    assert client.get(f"/v1/anomaly/uploads/{job_id}").json()["state"] == "queued"
    large_data.run_once()
    assert client.get(f"/v1/anomaly/uploads/{job_id}").json()["rows_done"] == 4
    assert "old incomplete" not in client.get(f"/v1/anomaly/uploads/{job_id}/findings").text


def test_cancel_during_processing_removes_data(client, monkeypatch):
    payload = ("amount\n" + "\n".join(str(n) for n in range(50))).encode()
    job_id = create(client, "cancel.csv", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    analyze = detector.analyze_rows

    def cancel_after_batch(*args, **kwargs):
        result = analyze(*args, **kwargs)
        assert client.delete(f"/v1/anomaly/uploads/{job_id}").json()["state"] == "cancelling"
        return result

    monkeypatch.setattr(detector, "analyze_rows", cancel_after_batch)
    large_data.run_once()
    assert client.get(f"/v1/anomaly/uploads/{job_id}").json()["state"] == "cancelled"
    assert client.get(f"/v1/anomaly/analyses/{job_id}").status_code == 404
    assert not (uploads.job_dir(job_id) / "source").exists()


def test_full_findings_export_is_not_capped_to_dashboard(client):
    payload = ("id,a,b,c,d\n" + "\n".join(f"{n},,,," for n in range(400))).encode()
    job_id = create(client, "findings.csv", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    large_data.run_once()
    report = client.get(f"/v1/anomaly/analyses/{job_id}").json()
    exported = client.get(f"/v1/anomaly/uploads/{job_id}/findings").text.splitlines()
    assert len(exported) == report["summary"]["total_anomalies"]
    assert len(exported) > 300
    assert len(report["anomalies"]) == min(300, len(exported))


def test_bulk_statistics_sample_all_batches_with_bounded_evidence(client, monkeypatch):
    monkeypatch.setattr(large_data, "BATCH_ROWS", 500)
    payload = ("id,amount\n" + "\n".join(f"{n},{n % 5 if n < 1500 else 10000 + n % 5}" for n in range(3000))).encode()
    job_id = create(client, "sample.csv", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    large_data.run_once()
    report = client.get(f"/v1/anomaly/analyses/{job_id}").json()
    graphs = report["statistical_graphs"]
    assert graphs["scope"] == "reservoir"
    assert graphs["statistics_rows"] == 2000
    assert graphs["total_rows"] == 3000
    assert len(graphs["points"]) <= 800
    assert graphs["columns"][0]["min"] < 5
    assert graphs["columns"][0]["max"] >= 10000
    assert max(point["row"] for point in graphs["points"]) > 2500
    assert sum(bin["normal"] + bin["outliers"] for bin in graphs["columns"][0]["histogram"]) == 2000


def test_bulk_preprocessing_aggregates_quality_and_preserves_original_evidence(client):
    lines = ["id,amount,status"]
    for n in range(1, 31):
        amount = "bad" if n == 22 else str(n)
        status = "unknown" if n % 2 == 0 else "approved"
        lines.append(f"{n},{amount},{status}")
    payload = "\n".join(lines).encode()
    job_id = create(client, "preparation.csv", payload)
    send(client, job_id, payload)
    client.post(f"/v1/anomaly/uploads/{job_id}/complete")
    large_data.run_once()
    report = client.get(f"/v1/anomaly/analyses/{job_id}").json()
    preparation = report["preprocessing"]
    assert preparation["scope"] == "batch"
    assert preparation["input_rows"] == preparation["output_rows"] == 30
    assert preparation["counts"]["missing_token"] == 15
    assert preparation["counts"]["invalid"] == 1
    assert report["summary"]["data_quality_score"] == round(100 * 74 / 90, 2)
    findings = [json.loads(line) for line in client.get(f"/v1/anomaly/uploads/{job_id}/findings").text.splitlines()]
    invalid = next(a for a in findings if a["row"] == 22 and a["type"] == "type_mismatch")
    assert invalid["original_value"] == "bad"
    assert invalid["prepared_value"] is None
    assert invalid["row_values"]["amount"] == "bad"
    assert invalid["prepared_row_values"]["amount"] is None
    amount_stats = next(c for c in report["statistical_graphs"]["columns"] if c["column"] == "amount")
    assert amount_stats["count"] == 29
