"""Section 8.3/8.5: structured JSON logs carry a correlation id from an
HTTP request through to job completion.
"""
import logging
import random
import uuid

import pytest
from arq.worker import Worker
from httpx import ASGITransport, AsyncClient

from sampling.api import app
from sampling.db.models import Dataset
from sampling.db.storage import save_file
from sampling.jobs.worker import WorkerSettings, get_pool
from tests.test_db_phase1 import AdminSessionFactory, _make_tenant_and_engagement
from tests.test_jobs_phase3 import _write_csv

pytestmark = pytest.mark.asyncio


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_correlation_id_generated_when_absent():
    async with _client() as client:
        resp = await client.get("/health")
    assert "X-Correlation-Id" in resp.headers
    assert len(resp.headers["X-Correlation-Id"]) == 32  # uuid4().hex


async def test_correlation_id_echoed_when_provided():
    async with _client() as client:
        resp = await client.get("/health", headers={"X-Correlation-Id": "my-trace-id-123"})
    assert resp.headers["X-Correlation-Id"] == "my-trace-id-123"


async def test_correlation_id_propagates_into_job_logs(tmp_path, caplog):
    tenant_id, eng_id = await _make_tenant_and_engagement("correlation-tenant")

    csv_path = _write_csv(tmp_path, n=20, seed=random.randint(1, 1_000_000_000))
    storage_key = save_file(tenant_id, str(csv_path), "d.csv")
    async with AdminSessionFactory() as session:
        dataset = Dataset(tenant_id=tenant_id, engagement_id=eng_id, filename="d.csv", storage_key=storage_key)
        session.add(dataset)
        await session.commit()
        dataset_id = dataset.id

    trace_id = f"trace-{uuid.uuid4().hex[:8]}"

    # Simulate what the middleware does for a real request carrying this
    # header (section 8.3): set_correlation_id() from the inbound header,
    # then enqueue -- enqueue_ingest_dataset reads get_correlation_id()
    # and passes it as an explicit job argument (contextvars don't cross
    # the process boundary to the ARQ worker).
    from sampling.observability import set_correlation_id
    from sampling.jobs.worker import enqueue_ingest_dataset
    set_correlation_id(trace_id)
    await enqueue_ingest_dataset(tenant_id, dataset_id)

    with caplog.at_level(logging.INFO, logger="sampling.jobs"):
        pool = await get_pool()
        worker = Worker(functions=WorkerSettings.functions, redis_pool=pool, burst=True, max_burst_jobs=10, poll_delay=0.05)
        await worker.async_run()
        await worker.close()

    matching = [r for r in caplog.records if getattr(r, "correlation_id", None) == trace_id]
    assert matching, f"no job log record carried correlation_id={trace_id}; saw {[getattr(r, 'correlation_id', None) for r in caplog.records]}"
