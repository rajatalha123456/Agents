import numpy as np
import pandas as pd
import pytest

from sampling.anomaly import EnsembleConfig
from sampling.audit_trail import AuditTrail
from sampling.engine import SamplingPolicy
from sampling.pipeline import RunConfig, run_pipeline, evaluate_run, benchmark_run
from sampling.risk import RiskWeights
from sampling.rules import load_rule_pack
from pathlib import Path

from sampling.api import app, assert_no_write_back_routes

RULE_PACK_PATH = Path(__file__).resolve().parents[1] / "rule_packs" / "payments_v1.3.0.yaml"


def _population(n=200, seed=3):
    rng = np.random.default_rng(seed)
    ids = [f"I{i:05d}" for i in range(n)]
    amounts = np.round(rng.exponential(1000, n), 2)
    approver_count = rng.integers(1, 3, n)
    posting_hour = rng.integers(0, 24, n)
    vendor_is_new = rng.integers(0, 2, n)
    vendor_txn = rng.integers(0, 30, n)
    return pd.DataFrame({
        "item_id": ids, "amount": amounts, "approver_count": approver_count,
        "posting_hour": posting_hour, "vendor_is_new": vendor_is_new,
        "vendor_transaction_count_30d": vendor_txn,
    })


def test_pipeline_runs_end_to_end(tmp_path):
    df = _population()
    pack = load_rule_pack(str(RULE_PACK_PATH))
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    config = RunConfig(
        tenant_id="t1",
        policy=SamplingPolicy(policy_version="v1", tolerable_misstatement=50_000, random_control_size=10),
        rule_pack=pack,
        risk_weights=RiskWeights.without_labels(),
        ensemble_config=EnsembleConfig(),
        run_id="run-1",
    )
    result = run_pipeline(df, config, trail)
    assert len(result.sample_result.items) > 0
    assert trail.verify().valid is True
    pack_result = result.evidence_pack()
    assert "run_id" in pack_result


def test_pipeline_reconstructable_from_trail_alone(tmp_path):
    df = _population()
    pack = load_rule_pack(str(RULE_PACK_PATH))
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    config = RunConfig(
        tenant_id="t1",
        policy=SamplingPolicy(policy_version="v1", tolerable_misstatement=50_000, random_control_size=5),
        rule_pack=pack,
        risk_weights=RiskWeights.without_labels(),
        ensemble_config=EnsembleConfig(),
        run_id="run-2",
    )
    run_pipeline(df, config, trail)
    stages = {e.action for e in trail.for_subject("run-2")}
    assert stages == {
        "pipeline.flags_added", "pipeline.rules_evaluated",
        "pipeline.anomaly_scored", "pipeline.risk_aggregated", "pipeline.sample_built",
    }


def test_evaluate_run_untested_items_reported_not_clean(tmp_path):
    df = _population()
    pack = load_rule_pack(str(RULE_PACK_PATH))
    trail = AuditTrail(str(tmp_path / "trail.jsonl"), tenant_id="t1")
    config = RunConfig(
        tenant_id="t1",
        policy=SamplingPolicy(policy_version="v1", tolerable_misstatement=50_000, random_control_size=10),
        rule_pack=pack,
        risk_weights=RiskWeights.without_labels(),
        ensemble_config=EnsembleConfig(),
        run_id="run-3",
    )
    result = run_pipeline(df, config, trail)
    items = result.sample_result.items
    interval = result.sample_result.manifest["mus_selection_metadata"].get("sampling_interval", 1000)

    tested_ids = list(items["item_id"])[: max(1, len(items) // 2)]
    audit_values = {i: float(items[items["item_id"] == i]["_amount"].iloc[0]) for i in tested_ids}

    projection = evaluate_run(result, audit_values, sampling_interval=interval,
                               confidence_level=0.95, tolerable_misstatement=50_000)
    if len(tested_ids) < len(items):
        assert any("untested" in w for w in projection.warnings)


def test_benchmark_run_wraps_benchmark_ranking():
    rng = np.random.default_rng(0)
    scores = rng.normal(size=500)
    labels = np.zeros(500)
    labels[:40] = 1
    result = benchmark_run(scores, labels, bootstrap_iterations=200, seed=1)
    assert result.verdict in (
        "BEATS_RANDOM", "WORSE_THAN_RANDOM", "NOT_DISTINGUISHABLE_FROM_RANDOM", "INSUFFICIENT_DATA",
    )


def test_no_write_back_routes():
    assert_no_write_back_routes()


def test_health_and_ready_endpoints():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"
