"""Phase 4 acceptance (section 6.5): LLM disabled tenant gets 409 (not a
silent skip); residency mismatch gets 409 (not a fallback); an ungrounded
narrative is withheld while the structured evidence is still returned.
"""
import random
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from sampling.auth.dependencies import DEFAULT_TENANT_ID
from sampling.db.models import Dataset, Engagement, RiskRun, Tenant
from tests.test_db_phase1 import AdminSessionFactory
from tests.test_jobs_phase3 import _make_policy, _make_queued_run, _write_csv
from sampling.jobs.ingest import ingest_dataset
from sampling.jobs.risk_run import execute_risk_run
from sampling.db.storage import save_file

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _reset_rate_limit():
    # Every request now resolves to the single fixed DEFAULT_TENANT_ID /
    # DEFAULT_USER_ID (no per-tenant tokens any more), so the Redis-backed
    # rate limiter's per-tenant/per-user buckets are shared with every
    # other test hitting the same route -- e.g. test_api_v1_conventions.py
    # deliberately exhausts the schema-suggest limit. Clear those buckets
    # before each test here so this file's own assertions aren't at the
    # mercy of what ran immediately before it in the same 60s window.
    from sampling.api_v1.rate_limit import _get_redis
    redis = _get_redis()
    keys = await redis.keys("ratelimit:*")
    if keys:
        await redis.delete(*keys)
    yield


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


async def test_schema_suggest_409_when_llm_disabled(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("llm-disabled-tenant")
    csv_path = _write_csv(tmp_path, n=20, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        tenant = await session.get(Tenant, tenant_id)
        # Reset explicitly rather than assume a fresh-row default: the
        # default tenant is shared across the whole suite now.
        tenant.llm_enabled = False
        tenant.llm_provider = None
        tenant.data_residency_region = "default"
        await session.commit()
        dataset_id = dataset.id

    async with _client() as client:
        resp = await client.post(f"/api/v1/datasets/{dataset_id}/schema-suggest")
    assert resp.status_code == 409
    assert "llm" in resp.json()["detail"].lower() or "disabled" in resp.json()["detail"].lower()


async def test_schema_suggest_409_on_residency_mismatch(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("llm-residency-tenant")
    csv_path = _write_csv(tmp_path, n=20, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        tenant = await session.get(Tenant, tenant_id)
        tenant.llm_enabled = True
        tenant.llm_provider = "default_provider"
        tenant.data_residency_region = "eu-only"  # provider has no confirmed EU endpoint
        await session.commit()
        dataset_id = dataset.id

    async with _client() as client:
        resp = await client.post(f"/api/v1/datasets/{dataset_id}/schema-suggest")
    assert resp.status_code == 409
    assert "residency" in resp.json()["detail"].lower() or "region" in resp.json()["detail"].lower()


async def test_schema_suggest_succeeds_when_llm_enabled_default_region(tmp_path):
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("llm-enabled-tenant")
    csv_path = _write_csv(tmp_path, n=20, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        tenant = await session.get(Tenant, tenant_id)
        tenant.llm_enabled = True
        tenant.llm_provider = "default_provider"
        tenant.data_residency_region = "default"
        await session.commit()
        dataset_id = dataset.id

    await ingest_dataset(tenant_id, dataset_id)

    async with _client() as client:
        resp = await client.post(f"/api/v1/datasets/{dataset_id}/schema-suggest")
    assert resp.status_code == 200, resp.text


async def test_narrate_withholds_ungrounded_narrative_but_returns_evidence(tmp_path, monkeypatch):
    # The stub client's default text has no numbers in it, so check_grounding
    # would trivially pass it (nothing to contradict). Give it a fabricated
    # figure not present in any item's evidence, to exercise withholding.
    from sampling.api_v1 import llm_gate
    monkeypatch.setattr(
        llm_gate.DummyLLMClient, "complete",
        lambda self, system, user, max_tokens=1500: "This item has a suspicious risk score of 987654.32.",
    )

    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("narrate-tenant")
    csv_path = _write_csv(tmp_path, n=50, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        tenant = await session.get(Tenant, tenant_id)
        tenant.llm_enabled = True
        tenant.llm_provider = "default_provider"
        tenant.data_residency_region = "default"
        await session.commit()
        dataset_id = dataset.id

    await ingest_dataset(tenant_id, dataset_id)
    async with AdminSessionFactory() as session:
        fingerprint = (await session.get(Dataset, dataset_id)).dataset_fingerprint

    policy_id = await _make_policy(tenant_id, eng_id)
    run_pk = await _make_queued_run(tenant_id, eng_id, dataset_id, policy_id, dataset_fingerprint=fingerprint)
    await execute_risk_run(tenant_id, run_pk)

    async with AdminSessionFactory() as session:
        run = await session.get(RiskRun, run_pk)
        run_id = run.run_id
        from sqlalchemy import select
        from sampling.db.models import SampleItem
        result = await session.execute(select(SampleItem.item_id).where(SampleItem.run_id == run_pk).limit(1))
        item_id = result.scalar_one()

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/risk-runs/{run_id}/items/{item_id}/narrate",
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # DummyLLMClient's fixed response text is not grounded in this item's
    # evidence, so the narrative must be withheld while evidence remains.
    assert body["narrative"] is None
    assert "fallback_message" in body
    assert body["evidence"]  # structured evidence still present
