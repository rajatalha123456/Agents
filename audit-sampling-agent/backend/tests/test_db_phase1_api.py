"""Section 3.6 acceptance: a run survives a server restart and is
retrievable by run_id, and re-sampling from stored data after a
simulated restart reproduces the identical selected item list.

"Restart" is simulated by disposing the module-level async engine/pool
and creating a fresh one bound to the same database -- the process-level
equivalent of a server restart for what these tests can actually observe
(the SQLAlchemy engine holding no in-memory state between calls).
"""
import uuid

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from sampling.auth.dependencies import DEFAULT_TENANT_ID
from sampling.db.models import Dataset, Engagement, SamplingPolicyRow, Tenant
from sampling.db.session import SessionFactory, engine, tenant_session
from sampling.determinism import dataset_fingerprint
from tests.test_db_phase1 import AdminSessionFactory, _make_dataset_with_rows

pytestmark = pytest.mark.asyncio


async def _make_engagement(name: str) -> uuid.UUID:
    # Every HTTP request now resolves to the single fixed DEFAULT_TENANT_ID
    # (no login/tenant headers any more), so test data seeded directly in
    # the DB must live under that same tenant to be visible through the API.
    async with AdminSessionFactory() as session:
        engagement = Engagement(tenant_id=DEFAULT_TENANT_ID, name=name, client_name="Client")
        session.add(engagement)
        await session.commit()
        return engagement.id


def _population(n=150, seed=11):
    rng = np.random.default_rng(seed)
    ids = [f"R{i:05d}" for i in range(n)]
    amounts = np.round(rng.exponential(1000, n), 2)
    return pd.DataFrame({"item_id": ids, "amount": amounts})


async def test_run_survives_restart_and_is_retrievable_by_run_id():
    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("restart-tenant")
    frame = _population()
    dataset_id = await _make_dataset_with_rows(tenant_id, eng_id, frame)

    async with AdminSessionFactory() as session:
        policy_row = SamplingPolicyRow(
            tenant_id=tenant_id, engagement_id=eng_id, policy_version="restart-v1",
            tolerable_misstatement=50_000, confidence_level=0.95,
        )
        session.add(policy_row)
        await session.commit()
        policy_id = policy_row.id

    run_id = f"restart-run-{uuid.uuid4().hex[:8]}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/runs", json={
            "engagement_id": str(eng_id),
            "dataset_id": str(dataset_id), "policy_id": str(policy_id),
            "policy_version": "restart-v1", "tolerable_misstatement": 50_000,
            "confidence_level": 0.95, "random_control_size": 10,
            "user_seed": "restart-seed", "run_id": run_id,
        })
        assert resp.status_code == 200, resp.text

    # Simulate a server restart: dispose the engine's connection pool so no
    # in-process state (cached connections included) survives.
    await engine.dispose()

    transport2 = ASGITransport(app=app)
    async with AsyncClient(transport=transport2, base_url="http://test") as client:
        resp = await client.get(f"/runs/{run_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()

    assert body["run_id"] == run_id
    assert body["status"] == "complete"
    assert len(body["selected_item_ids"]) > 0
    return body["selected_item_ids"], tenant_id, dataset_id


async def test_reproducibility_same_dataset_policy_seed_across_restart():
    from sampling.db.repositories import load_population
    from sampling.engine import SamplingPolicy, build_sample

    tenant_id = DEFAULT_TENANT_ID
    eng_id = await _make_engagement("repro-tenant")
    frame = _population(seed=22)
    dataset_id = await _make_dataset_with_rows(tenant_id, eng_id, frame)

    async with AdminSessionFactory() as session:
        policy_row = SamplingPolicyRow(
            tenant_id=tenant_id, engagement_id=eng_id, policy_version="repro-v1",
            tolerable_misstatement=40_000, confidence_level=0.95,
        )
        session.add(policy_row)
        await session.commit()
        policy_id = policy_row.id

    run_id = f"repro-run-{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/runs", json={
            "engagement_id": str(eng_id),
            "dataset_id": str(dataset_id), "policy_id": str(policy_id),
            "policy_version": "repro-v1", "tolerable_misstatement": 40_000,
            "confidence_level": 0.95, "random_control_size": 5,
            "user_seed": "repro-seed", "run_id": run_id,
        })
        assert resp.status_code == 200, resp.text

    async with tenant_session(tenant_id) as session:
        from sampling.db.run_repository import load_run_by_run_id, load_sample_item_ids
        run_before = await load_run_by_run_id(session, run_id)
        ids_before = await load_sample_item_ids(session, run_before.id)

    # Simulate restart.
    await engine.dispose()

    # Rebuild the sample fresh from stored data with the same seed/policy --
    # this must reproduce the identical selected item list.
    async with tenant_session(tenant_id) as session:
        reloaded_frame = await load_population(session, dataset_id)

    policy = SamplingPolicy(
        policy_version="repro-v1", tolerable_misstatement=40_000,
        confidence_level=0.95, random_control_size=5,
    )
    rebuilt = build_sample(reloaded_frame, policy, user_seed="repro-seed")
    ids_after = sorted(rebuilt.items["item_id"])

    assert sorted(ids_before) == ids_after
