"""ARQ worker settings and enqueue helpers.

ARQ (asyncio + redis) was chosen over Celery because the entire backend
is already async (SQLAlchemy async engine, asyncpg) -- Celery's worker
model is fundamentally synchronous and would need a sync DB path bolted
on just for jobs.
"""
from __future__ import annotations

import logging
import os
import uuid

from arq import cron
from arq.connections import ArqRedis, RedisSettings, create_pool

from ..observability import (
    configure_logging,
    get_correlation_id,
    log_with_fields,
    new_correlation_id,
    set_correlation_id,
)
from .audit_anchor import anchor_audit_trail_all_tenants
from .benchmark import run_benchmark as _run_benchmark
from .evidence import build_evidence_pack as _build_evidence_pack
from .ingest import ingest_dataset as _ingest_dataset
from .reaper import reap_stale_runs_all_tenants
from .risk_run import execute_risk_run as _execute_risk_run

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:16379")

logger = logging.getLogger("sampling.jobs")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(REDIS_URL)


async def _on_startup(ctx) -> None:
    configure_logging()


# --- job wrappers: arq passes (ctx, *args); ctx is unused by our jobs
# beyond the correlation id. Contextvars set by the HTTP request that
# enqueued this job do not cross the process boundary to this worker, so
# each wrapper takes correlation_id explicitly and re-establishes it here
# -- that's what makes a log line inside the job traceable back to the
# request that triggered it (section 8.3, 8.5).

def _job_logger(job_name: str, correlation_id: str | None):
    set_correlation_id(correlation_id or new_correlation_id())
    log_with_fields(logger, logging.INFO, f"{job_name} started", job=job_name)


async def ingest_dataset_job(ctx, tenant_id: str, dataset_id: str, correlation_id: str | None = None, **kwargs) -> dict:
    _job_logger("ingest_dataset", correlation_id)
    result = await _ingest_dataset(uuid.UUID(tenant_id), uuid.UUID(dataset_id), **kwargs)
    log_with_fields(logger, logging.INFO, "ingest_dataset completed", job="ingest_dataset", **{
        k: v for k, v in result.items() if k in ("status", "row_count")
    })
    return result


async def execute_risk_run_job(ctx, tenant_id: str, run_pk: str, actor: str = "system", correlation_id: str | None = None) -> dict:
    _job_logger("execute_risk_run", correlation_id)
    result = await _execute_risk_run(uuid.UUID(tenant_id), uuid.UUID(run_pk), actor=actor)
    log_with_fields(logger, logging.INFO, "execute_risk_run completed", job="execute_risk_run", **result)
    return result


async def run_benchmark_job(ctx, tenant_id: str, run_pk: str, label_col: str,
                             labels_by_item_id: dict, actor: str = "system", correlation_id: str | None = None) -> dict:
    _job_logger("run_benchmark", correlation_id)
    return await _run_benchmark(uuid.UUID(tenant_id), uuid.UUID(run_pk), label_col, labels_by_item_id, actor=actor)


async def build_evidence_pack_job(ctx, tenant_id: str, run_pk: str, actor: str = "system", correlation_id: str | None = None) -> dict:
    _job_logger("build_evidence_pack", correlation_id)
    return await _build_evidence_pack(uuid.UUID(tenant_id), uuid.UUID(run_pk), actor=actor)


async def reap_stale_runs_job(ctx) -> dict:
    _job_logger("reap_stale_runs", None)
    return await reap_stale_runs_all_tenants()


async def anchor_audit_trail_job(ctx) -> dict:
    _job_logger("anchor_audit_trail", None)
    return await anchor_audit_trail_all_tenants()


class WorkerSettings:
    functions = [
        ingest_dataset_job, execute_risk_run_job, run_benchmark_job,
        build_evidence_pack_job, reap_stale_runs_job, anchor_audit_trail_job,
    ]
    cron_jobs = [
        cron(reap_stale_runs_job, minute=set(range(0, 60, 5))),  # every 5 minutes
        cron(anchor_audit_trail_job, hour=2, minute=0),  # nightly at 02:00
    ]
    redis_settings = _redis_settings()
    on_startup = _on_startup


# --- enqueue helpers used by the API -------------------------------------

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
    return _pool


async def enqueue_ingest_dataset(tenant_id: uuid.UUID, dataset_id: uuid.UUID, **kwargs) -> str:
    pool = await get_pool()
    job = await pool.enqueue_job(
        "ingest_dataset_job", str(tenant_id), str(dataset_id), correlation_id=get_correlation_id(), **kwargs
    )
    return job.job_id


async def enqueue_execute_risk_run(tenant_id: uuid.UUID, run_pk: uuid.UUID, actor: str = "system") -> str:
    pool = await get_pool()
    job = await pool.enqueue_job(
        "execute_risk_run_job", str(tenant_id), str(run_pk), actor=actor, correlation_id=get_correlation_id(),
    )
    return job.job_id
