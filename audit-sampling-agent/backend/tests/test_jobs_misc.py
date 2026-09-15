"""Coverage for the remaining Phase 3 jobs: run_benchmark, build_evidence_pack,
anchor_audit_trail.
"""
import uuid

import pytest

from sampling.db.models import Dataset
from sampling.db.storage import save_file
from sampling.jobs.audit_anchor import anchor_audit_trail
from sampling.jobs.benchmark import run_benchmark
from sampling.jobs.evidence import build_evidence_pack
from sampling.jobs.ingest import ingest_dataset
from sampling.jobs.risk_run import execute_risk_run
from tests.test_db_phase1 import AdminSessionFactory, _make_tenant_and_engagement
from tests.test_jobs_phase3 import _make_policy, _make_queued_run, _write_csv

pytestmark = pytest.mark.asyncio


async def _make_completed_run(tmp_path, tenant_id, eng_id, n=100):
    csv_path = _write_csv(tmp_path, n=n)
    storage_key = save_file(tenant_id, str(csv_path), "data.csv")
    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="data.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id

    await ingest_dataset(tenant_id, dataset_id)
    async with AdminSessionFactory() as session:
        fingerprint = (await session.get(Dataset, dataset_id)).dataset_fingerprint

    policy_id = await _make_policy(tenant_id, eng_id)
    run_pk = await _make_queued_run(tenant_id, eng_id, dataset_id, policy_id, dataset_fingerprint=fingerprint)
    await execute_risk_run(tenant_id, run_pk)
    return run_pk


async def test_run_benchmark_job_produces_a_verdict(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("bench-job-tenant")
    run_pk = await _make_completed_run(tmp_path, tenant_id, eng_id, n=150)

    from sampling.db.models import RiskScore
    from sqlalchemy import select
    async with AdminSessionFactory() as session:
        result = await session.execute(select(RiskScore).where(RiskScore.run_id == run_pk))
        item_ids = [r.item_id for r in result.scalars()]

    # A deterministic (fake) label set: half the items are "findings".
    labels = {item_id: float(i % 2 == 0) for i, item_id in enumerate(item_ids)}

    result = await run_benchmark(tenant_id, run_pk, "synthetic", labels)
    assert result["verdict"] in (
        "BEATS_RANDOM", "WORSE_THAN_RANDOM", "NOT_DISTINGUISHABLE_FROM_RANDOM", "INSUFFICIENT_DATA",
    )
    assert result["statement"]


async def test_build_evidence_pack_job_assembles_pack(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("evidence-job-tenant")
    run_pk = await _make_completed_run(tmp_path, tenant_id, eng_id, n=80)

    pack = await build_evidence_pack(tenant_id, run_pk)
    assert pack["dataset_fingerprint"]
    assert len(pack["sample_items"]) > 0
    assert "sample_manifest" in pack


async def test_build_evidence_pack_rejects_incomplete_run():
    tenant_id, eng_id = await _make_tenant_and_engagement("evidence-incomplete-tenant")
    from sampling.db.models import RiskRun
    from tests.test_db_phase1 import _make_dataset_with_rows
    import pandas as pd

    frame = pd.DataFrame({"item_id": ["a", "b"], "amount": [1.0, 2.0]})
    dataset_id = await _make_dataset_with_rows(tenant_id, eng_id, frame)
    policy_id = await _make_policy(tenant_id, eng_id)

    async with AdminSessionFactory() as session:
        run = RiskRun(tenant_id=tenant_id, engagement_id=eng_id, dataset_id=dataset_id, policy_id=policy_id,
                       run_id=f"incomplete-{uuid.uuid4().hex[:8]}", status="running", dataset_fingerprint="fp")
        session.add(run)
        await session.commit()
        run_pk = run.id

    with pytest.raises(ValueError, match="cannot build an evidence pack"):
        await build_evidence_pack(tenant_id, run_pk)


async def test_anchor_audit_trail_writes_anchor(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("anchor-job-tenant")
    run_pk = await _make_completed_run(tmp_path, tenant_id, eng_id, n=30)  # generates audit events

    result = await anchor_audit_trail(tenant_id)
    assert result["anchor_id"]
    assert result["head_sequence"] is not None
