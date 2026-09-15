"""Additional coverage for Phase 4 routes not exercised by the main e2e
flow: tenant admin, rule packs (create/validate/dry-run/approve), dataset
preview/profile/delete, engagement patch, bulk audit values, risk-run
cancel/transactions-filter, and the 501 stub export routes.
"""
import io
import random
import uuid

import numpy as np
import pandas as pd
import pytest
from arq.worker import Worker
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from sampling.auth.dependencies import DEFAULT_TENANT_ID
from sampling.db.models import Dataset, Engagement
from sampling.db.storage import save_file
from sampling.jobs.ingest import ingest_dataset
from sampling.jobs.worker import WorkerSettings, get_pool
from tests.test_db_phase1 import AdminSessionFactory, _make_tenant_and_engagement
from tests.test_jobs_phase3 import RULE_PACK_YAML, _make_policy, _make_queued_run, _write_csv

pytestmark = pytest.mark.asyncio


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _make_engagement(name: str) -> uuid.UUID:
    # Every HTTP request now resolves to the single fixed DEFAULT_TENANT_ID
    # (no login/tenant headers any more), so test data seeded directly in
    # the DB must live under that same tenant to be visible through the API.
    async with AdminSessionFactory() as session:
        engagement = Engagement(tenant_id=DEFAULT_TENANT_ID, name=name, client_name="Client")
        session.add(engagement)
        await session.commit()
        return engagement.id


async def _run_burst_worker() -> None:
    pool = await get_pool()
    worker = Worker(functions=WorkerSettings.functions, redis_pool=pool, burst=True, max_burst_jobs=10, poll_delay=0.05)
    await worker.async_run()
    await worker.close()


async def test_tenant_admin_routes(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("tenant-admin-cov")

    async with _client() as client:
        resp = await client.get("/api/v1/tenant")
        assert resp.status_code == 200

        resp = await client.patch("/api/v1/tenant", json={"name": "Renamed Tenant"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Tenant"

        resp = await client.get("/api/v1/tenant/llm-config")
        assert resp.status_code == 200

        resp = await client.put("/api/v1/tenant/llm-config",
                                 json={"llm_enabled": True, "llm_provider": "default_provider", "llm_model": "stub-1"})
        assert resp.status_code == 200
        assert resp.json()["llm_enabled"] is True

        resp = await client.get("/api/v1/tenant/users")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        resp = await client.post("/api/v1/tenant/users", json={
            "email": f"invitee+{uuid.uuid4().hex[:8]}@cov.com", "role": "viewer", "temporary_password": "temp1234",
        })
        assert resp.status_code == 200
        new_user_id = resp.json()["id"]

        resp = await client.patch(f"/api/v1/tenant/users/{new_user_id}",
                                   json={"role": "auditor", "is_active": False})
        assert resp.status_code == 200
        assert resp.json()["role"] == "auditor"
        assert resp.json()["is_active"] is False


async def test_engagement_patch_and_get():
    tenant_id, eng_id = await _make_tenant_and_engagement("engagement-patch-cov")

    async with _client() as client:
        resp = await client.post("/api/v1/engagements", json={"name": "E1", "client_name": "C1"})
        engagement_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/engagements/{engagement_id}")
        assert resp.status_code == 200

        resp = await client.patch(f"/api/v1/engagements/{engagement_id}",
                                   json={"status": "closed", "performance_materiality": 5000})
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"


async def test_rule_pack_create_validate_dry_run_approve(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("rulepack-cov")

    csv_path = _write_csv(tmp_path, n=40, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")
    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id
    await ingest_dataset(tenant_id, dataset_id)

    # Unique pack_version per call (not the shared constant's "1.0.0"):
    # every HTTP request now resolves to the single fixed DEFAULT_TENANT_ID
    # post auth-removal, so a fixed version would collide with a prior run
    # on the (tenant_id, pack_id, pack_version) uniqueness constraint.
    rule_pack_yaml = RULE_PACK_YAML.replace('pack_version: "1.0.0"', f'pack_version: "{uuid.uuid4().hex[:8]}"')

    async with _client() as client:
        resp = await client.post("/api/v1/rule-packs/validate", json={"yaml_source": rule_pack_yaml})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

        resp = await client.post("/api/v1/rule-packs", json={"yaml_source": rule_pack_yaml})
        assert resp.status_code == 200, resp.text
        rule_pack_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/rule-packs/{rule_pack_id}")
        assert resp.status_code == 200

        resp = await client.get("/api/v1/rule-packs")
        assert resp.status_code == 200

        resp = await client.post(f"/api/v1/rule-packs/{rule_pack_id}/dry-run",
                                  params={"dataset_id": str(dataset_id)})
        assert resp.status_code == 200, resp.text
        assert "big_amount" in resp.json()["hit_counts"]

        # removed: SoD self-approval rejection no longer applicable, single
        # fixed admin user post auth-removal always approves successfully.
        resp = await client.post(f"/api/v1/rule-packs/{rule_pack_id}/approve")
        assert resp.status_code == 200


async def test_dataset_preview_profile_delete(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("dataset-cov")

    csv_path = _write_csv(tmp_path, n=30, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")
    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id
    await ingest_dataset(tenant_id, dataset_id)

    async with _client() as client:
        resp = await client.get(f"/api/v1/datasets/{dataset_id}/preview?n=5")
        assert resp.status_code == 200
        assert len(resp.json()["rows"]) == 5

        resp = await client.get(f"/api/v1/datasets/{dataset_id}/profile")
        assert resp.status_code == 200
        assert resp.json()["schema_profile"] is not None

        resp = await client.put(f"/api/v1/datasets/{dataset_id}/column-mapping",
                                 json={"item_id_col": "item_id", "amount_col": "amount"})
        assert resp.status_code == 200

        resp = await client.get("/api/v1/datasets")
        assert resp.status_code == 200

        # removed: RBAC-across-roles (auditor vs admin) no longer applicable,
        # every request now resolves to the same fixed admin user.
        resp = await client.delete(f"/api/v1/datasets/{dataset_id}")
        assert resp.status_code == 204


async def test_bulk_audit_values_and_evidence_stub_exports_and_cancel(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("bulk-cov")

    csv_path = _write_csv(tmp_path, n=60, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")
    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id
    await ingest_dataset(tenant_id, dataset_id)
    async with AdminSessionFactory() as session:
        fingerprint = (await session.get(Dataset, dataset_id)).dataset_fingerprint

    policy_id = await _make_policy(tenant_id, eng_id)
    from sampling.jobs.risk_run import execute_risk_run
    run_pk = await _make_queued_run(tenant_id, eng_id, dataset_id, policy_id, dataset_fingerprint=fingerprint)
    await execute_risk_run(tenant_id, run_pk)

    async with AdminSessionFactory() as session:
        from sampling.db.models import RiskRun, SampleItem
        from sqlalchemy import select
        run = await session.get(RiskRun, run_pk)
        run_id = run.run_id
        result = await session.execute(select(SampleItem.item_id).where(SampleItem.run_id == run_pk))
        item_ids = [r[0] for r in result]

    csv_content = "item_id,audit_value\n" + "\n".join(f"{i},1.00" for i in item_ids[:3])

    async with _client() as client:
        files = {"file": ("values.csv", csv_content.encode(), "text/csv")}
        resp = await client.post(f"/api/v1/risk-runs/{run_id}/audit-values/bulk", files=files)
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated"] == 3

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/evidence-pack.pdf")
        assert resp.status_code == 501

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/sample.xlsx")
        assert resp.status_code == 501

        resp = await client.get(f"/api/v1/risk-runs/{run_id}/transactions?stratum=random_control&sort_by=amount")
        assert resp.status_code == 200

        # Cannot cancel an already-complete run.
        resp = await client.post(f"/api/v1/risk-runs/{run_id}/cancel")
        assert resp.status_code == 409
