"""Stale run reaper: a worker that dies mid-job (killed, crashed, OOM)
leaves its risk_runs row stuck at status='running' forever unless
something else notices. This scans for runs that have been 'running'
longer than a stale threshold with no progress and marks them 'failed'
explicitly, rather than leaving a run silently running forever.

Scheduled as a periodic ARQ cron job in worker.py.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import RiskRun, Tenant
from ..db.session import SessionFactory, tenant_session

STALE_RUN_TIMEOUT = dt.timedelta(minutes=30)


async def reap_stale_runs_for_tenant(tenant_id: uuid.UUID, now: dt.datetime | None = None) -> list[str]:
    now = now or dt.datetime.now(dt.UTC)
    reaped: list[str] = []

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(RiskRun).where(RiskRun.tenant_id == tenant_id, RiskRun.status == "running")
        )
        stale_runs = [r for r in result.scalars() if r.started_at and (now - r.started_at) > STALE_RUN_TIMEOUT]

        trail = PgAuditTrail(tenant_id)
        for run in stale_runs:
            run.status = "failed"
            run.error_message = (
                f"run exceeded the stale-run timeout ({STALE_RUN_TIMEOUT}) with no "
                "completion signal; the worker likely died or was killed mid-run."
            )
            run.completed_at = now
            await trail.append(
                session, actor="system.reaper", action="risk_run.reaped", subject=str(run.id),
                payload={"run_id": run.run_id, "started_at": run.started_at.isoformat()},
            )
            reaped.append(run.run_id)

    return reaped


async def reap_stale_runs_all_tenants(now: dt.datetime | None = None) -> dict[str, list[str]]:
    async with SessionFactory() as session:
        result = await session.execute(select(Tenant.id))
        tenant_ids = [r[0] for r in result]

    reaped_by_tenant: dict[str, list[str]] = {}
    for tenant_id in tenant_ids:
        reaped = await reap_stale_runs_for_tenant(tenant_id, now=now)
        if reaped:
            reaped_by_tenant[str(tenant_id)] = reaped
    return reaped_by_tenant
