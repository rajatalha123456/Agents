"""BENCHMARK routes (section 6.1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.models import Benchmark, RiskRun
from ..db.session import tenant_session
from ..jobs.benchmark import run_benchmark as _run_benchmark

router = APIRouter(prefix="/api/v1/risk-runs", tags=["benchmark"])


async def _get_run_or_404(session, run_id: str) -> RiskRun:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


class BenchmarkRequest(BaseModel):
    label_source: str
    labels_by_item_id: dict[str, float]


@router.post("/{run_id}/benchmark", dependencies=[Depends(require_role("auditor"))])
async def create_benchmark(run_id: str, req: BenchmarkRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        run_pk = run.id

    result = await _run_benchmark(uuid.UUID(user.tenant_id), run_pk, req.label_source, req.labels_by_item_id, actor=user.user_id)
    return result


@router.get("/{run_id}/benchmark")
async def get_benchmark(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(
            select(Benchmark).where(Benchmark.run_id == run.id).order_by(Benchmark.created_at.desc()).limit(1)
        )
        benchmark = result.scalar_one_or_none()
    if benchmark is None:
        raise HTTPException(status_code=404, detail="no benchmark exists for this run")
    return {"verdict": benchmark.verdict, "report": benchmark.report}
