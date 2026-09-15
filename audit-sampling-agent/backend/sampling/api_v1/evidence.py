"""EVIDENCE routes (section 6.1). PDF/XLSX generation is not implemented
here -- CSV and JSON are, since a PDF/XLSX renderer is a separate library
choice the spec doesn't mandate and building one wasn't the priority for
this pass. The .pdf and .xlsx routes exist and say so explicitly (501)
rather than silently returning something else.
"""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..auth.dependencies import CurrentUser, get_current_user
from ..db.models import RiskRun, SampleItem
from ..db.session import tenant_session
from ..jobs.worker import get_pool
from .money import money_str

router = APIRouter(prefix="/api/v1/risk-runs", tags=["evidence"])


async def _get_run_or_404(session, run_id: str) -> RiskRun:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/{run_id}/evidence-pack", status_code=202)
async def build_evidence_pack_route(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        run_pk = run.id

    pool = await get_pool()
    job = await pool.enqueue_job("build_evidence_pack_job", str(user.tenant_id), str(run_pk), actor=user.user_id)
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/{run_id}/evidence-pack")
async def get_evidence_pack(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    from ..jobs.evidence import build_evidence_pack
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        run_pk = run.id
    try:
        return await build_evidence_pack(uuid.UUID(user.tenant_id), run_pk, actor=user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{run_id}/evidence-pack.pdf")
async def get_evidence_pack_pdf(run_id: str, user: CurrentUser = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="PDF workpaper export is not implemented in this build")


@router.get("/{run_id}/sample.csv")
async def get_sample_csv(run_id: str, user: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        items = list(result.scalars())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["item_id", "stratum", "selection_basis", "projectable", "amount", "audit_value"])
    for i in items:
        writer.writerow([i.item_id, i.stratum, i.selection_basis, i.projectable, money_str(i.amount), money_str(i.audit_value)])
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="text/csv",
                              headers={"Content-Disposition": f"attachment; filename={run_id}_sample.csv"})


@router.get("/{run_id}/sample.xlsx")
async def get_sample_xlsx(run_id: str, user: CurrentUser = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="XLSX export is not implemented in this build; use sample.csv")
