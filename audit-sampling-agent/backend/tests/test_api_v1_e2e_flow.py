"""End-to-end smoke test through the Phase 4 /api/v1 surface: create an
engagement, upload a dataset (through the real queue), create a policy,
launch a risk run (through the real queue), review the sample, enter
audit values, evaluate, raise an override, run a benchmark, and pull the
evidence pack -- proving the routers actually integrate, not just import.
"""
import io
import uuid

import numpy as np
import pandas as pd
import pytest
from arq.worker import Worker
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from sampling.jobs.worker import WorkerSettings, get_pool
from tests.test_db_phase1 import _make_tenant_and_engagement

pytestmark = pytest.mark.asyncio


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _run_burst_worker() -> None:
    pool = await get_pool()
    worker = Worker(functions=WorkerSettings.functions, redis_pool=pool, burst=True, max_burst_jobs=10, poll_delay=0.05)
    await worker.async_run()
    await worker.close()


def _csv_bytes(n=200, seed=None) -> bytes:
    # Random per call (not a fixed seed): every HTTP request now resolves
    # to the single fixed DEFAULT_TENANT_ID post auth-removal, so repeated
    # test runs would otherwise upload byte-identical files and collide on
    # the (tenant_id, file_sha256) uniqueness constraint.
    if seed is None:
        seed = uuid.uuid4().int % (2**31)
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "item_id": [f"E{i:06d}" for i in range(n)],
        "amount": np.round(rng.exponential(1000, n), 2),
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


async def test_full_engagement_to_evidence_pack_flow():
    tenant_id, _ = await _make_tenant_and_engagement("e2e-flow-tenant")

    async with _client() as client:
        # 1. Create engagement.
        resp = await client.post("/api/v1/engagements",
                                  json={"name": "E2E Engagement", "client_name": "ACME"})
        assert resp.status_code == 200, resp.text
        engagement_id = resp.json()["id"]

        # 2. Upload dataset (multipart -> job).
        files = {"file": ("data.csv", _csv_bytes(), "text/csv")}
        resp = await client.post(f"/api/v1/datasets?engagement_id={engagement_id}", files=files)
        assert resp.status_code == 202, resp.text
        dataset_id = resp.json()["id"]

    await _run_burst_worker()

    async with _client() as client:
        resp = await client.get(f"/api/v1/datasets/{dataset_id}")
        assert resp.status_code == 200
        assert resp.json()["ingestion_status"] == "complete"
        assert resp.json()["row_count"] == 200

        # 3. Create policy.
        resp = await client.post("/api/v1/policies", json={
            "engagement_id": engagement_id, "policy_version": "e2e-v1",
            "tolerable_misstatement": 30000, "random_control_size": 10,
        })
        assert resp.status_code == 200, resp.text
        policy_id = resp.json()["id"]

        # Approve the policy.
        resp = await client.post(f"/api/v1/policies/{policy_id}/approve")
        assert resp.status_code == 200, resp.text

        # 4. Launch risk run (-> 202 + job id).
        run_id = f"e2e-run-{uuid.uuid4().hex[:8]}"
        resp = await client.post("/api/v1/risk-runs", json={
            "engagement_id": engagement_id, "dataset_id": dataset_id, "policy_id": policy_id,
            "run_id": run_id, "user_seed": "e2e-seed",
        })
        assert resp.status_code == 202, resp.text

    await _run_burst_worker()

    async with _client() as client:
        # 5. Run status + sample review.
        resp = await client.get(f"/api/v1/risk-runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "complete"

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/sample")
        assert resp.status_code == 200
        sample_items = resp.json()["items"]
        assert len(sample_items) > 0

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/strata")
        assert resp.status_code == 200
        assert len(resp.json()["strata"]) > 0

        # 6. Enter audit values (mark every sample item tested = book value,
        # i.e. no misstatement, so the evaluation should ACCEPT).
        for item in sample_items:
            resp = await client.put(
                f"/api/v1/risk-runs/{run_id}/items/{item['item_id']}/audit-value",
                json={"audit_value": float(item["amount"])},
            )
            assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/testing-progress")
        assert resp.status_code == 200
        assert resp.json()["untested_count"] == 0

        # 7. Evaluate.
        resp = await client.post(
            f"/api/v1/risk-runs/{run_id}/evaluate?tolerable_misstatement=30000",
        )
        assert resp.status_code == 200, resp.text
        evaluation_id = resp.json()["evaluation_id"]
        assert resp.json()["workpaper"]["conclusion"] == "ACCEPT"

        # Sign off the evaluation.
        resp = await client.post(
            f"/api/v1/risk-runs/{run_id}/evaluation/sign-off",
            json={"evaluation_id": evaluation_id},
        )
        assert resp.status_code == 200, resp.text

        # 8. Raise a challenge / override on the first sample item.
        item_id = sample_items[0]["item_id"]
        resp = await client.get(f"/api/v1/risk-runs/{run_id}/items/{item_id}/explanation")
        assert resp.status_code == 200
        assert resp.json()["selected"] is True

        resp = await client.post(f"/api/v1/risk-runs/{run_id}/override", json={
            "item_id": item_id, "action": "accept",
            "reason": "Reviewed supporting documentation; item is a valid transaction.",
        })
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/overrides")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # 9. Benchmark (synthetic labels).
        resp = await client.get(f"/api/v1/risk-runs/{run_id}/transactions?limit=500")
        assert resp.status_code == 200
        txn_items = resp.json()["items"]
        labels = {t["item_id"]: float(i % 5 == 0) for i, t in enumerate(txn_items)}
        resp = await client.post(f"/api/v1/risk-runs/{run_id}/benchmark",
                                  json={"label_source": "synthetic", "labels_by_item_id": labels})
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/benchmark")
        assert resp.status_code == 200
        assert resp.json()["verdict"]

        # 10. Evidence pack (JSON) and sample CSV export.
        resp = await client.get(f"/api/v1/risk-runs/{run_id}/evidence-pack")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/sample.csv")
        assert resp.status_code == 200
        assert b"item_id" in resp.content

        # 11. Audit trail: verify chain, list events.
        resp = await client.get("/api/v1/audit-events/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

        resp = await client.get("/api/v1/audit-events")
        assert resp.status_code == 200
        assert resp.json()["total"] > 0
