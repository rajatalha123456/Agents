"""End-to-end proof that the ARQ + Redis queue plumbing itself works:
enqueue a real job through the pool, run a burst worker against the real
Redis instance, and confirm the database was updated -- not just that the
job function works when called directly in-process (that's already
covered by test_jobs_phase3.py).
"""
import uuid

import pytest
from arq.worker import Worker

from sampling.db.models import Dataset, RiskRun
from sampling.db.storage import save_file
from sampling.jobs.worker import WorkerSettings, enqueue_execute_risk_run, enqueue_ingest_dataset, get_pool
from tests.test_db_phase1 import AdminSessionFactory, _make_tenant_and_engagement
from tests.test_jobs_phase3 import _make_policy, _make_queued_run, _write_csv

pytestmark = pytest.mark.asyncio


async def _run_burst_worker() -> None:
    pool = await get_pool()
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_pool=pool,
        burst=True,
        max_burst_jobs=10,
        poll_delay=0.05,
    )
    await worker.async_run()
    await worker.close()


async def test_ingest_dataset_job_runs_through_real_queue(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("queue-ingest-tenant")
    csv_path = _write_csv(tmp_path, n=40)
    storage_key = save_file(tenant_id, str(csv_path), "data.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="data.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id

    job_id = await enqueue_ingest_dataset(tenant_id, dataset_id)
    assert job_id

    await _run_burst_worker()

    async with AdminSessionFactory() as session:
        dataset = await session.get(Dataset, dataset_id)
    assert dataset.ingestion_status == "complete"
    assert dataset.row_count == 40


async def test_execute_risk_run_job_runs_through_real_queue(tmp_path):
    tenant_id, eng_id = await _make_tenant_and_engagement("queue-run-tenant")
    csv_path = _write_csv(tmp_path, n=60)
    storage_key = save_file(tenant_id, str(csv_path), "data.csv")

    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="data.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id

    ingest_job_id = await enqueue_ingest_dataset(tenant_id, dataset_id)
    await _run_burst_worker()

    async with AdminSessionFactory() as session:
        fingerprint = (await session.get(Dataset, dataset_id)).dataset_fingerprint

    policy_id = await _make_policy(tenant_id, eng_id)
    run_pk = await _make_queued_run(tenant_id, eng_id, dataset_id, policy_id, dataset_fingerprint=fingerprint)

    run_job_id = await enqueue_execute_risk_run(tenant_id, run_pk)
    assert run_job_id
    await _run_burst_worker()

    async with AdminSessionFactory() as session:
        run = await session.get(RiskRun, run_pk)
    assert run.status == "complete"
    assert run.progress_pct == 100
