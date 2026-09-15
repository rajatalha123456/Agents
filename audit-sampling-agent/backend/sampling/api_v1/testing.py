"""TESTING routes (section 6.1): entering audit values, evaluating the
sample, and sign-off. Untested items are reported as untested, never as
clean (section 7.3's UI rule mirrors this API-side).
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Evaluation, RiskRun, SampleItem
from ..db.session import tenant_session
from ..evaluation import project_misstatement, tested_items_from_frame
from .money import money_str

router = APIRouter(prefix="/api/v1/risk-runs", tags=["testing"])


class AuditValueRequest(BaseModel):
    audit_value: float
    note: str | None = None


async def _get_run_or_404(session, run_id: str) -> RiskRun:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.put("/{run_id}/items/{item_id}/audit-value", dependencies=[Depends(require_role("auditor"))])
async def set_audit_value(run_id: str, item_id: str, req: AuditValueRequest,
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(
            select(SampleItem).where(SampleItem.run_id == run.id, SampleItem.item_id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="sample item not found")

        item.audit_value = req.audit_value
        item.tested_by = uuid.UUID(user.user_id)
        item.tested_at = datetime.now(UTC)
        item.tester_note = req.note

    return {"item_id": item_id, "audit_value": money_str(req.audit_value)}


@router.post("/{run_id}/audit-values/bulk", dependencies=[Depends(require_role("auditor"))])
async def bulk_audit_values(run_id: str, file: UploadFile,
                             user: CurrentUser = Depends(get_current_user)) -> dict:
    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if "item_id" not in reader.fieldnames or "audit_value" not in reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV must have item_id and audit_value columns")

    updated, missing = 0, []
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        for row in rows:
            result = await session.execute(
                select(SampleItem).where(SampleItem.run_id == run.id, SampleItem.item_id == row["item_id"])
            )
            item = result.scalar_one_or_none()
            if item is None:
                missing.append(row["item_id"])
                continue
            item.audit_value = float(row["audit_value"])
            item.tested_by = uuid.UUID(user.user_id)
            item.tested_at = datetime.now(UTC)
            updated += 1

    return {"updated": updated, "missing_item_ids": missing}


@router.get("/{run_id}/testing-progress")
async def testing_progress(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        items = list(result.scalars())

    tested = [i for i in items if i.audit_value is not None]
    return {
        "total_sample_items": len(items),
        "tested_count": len(tested),
        "untested_count": len(items) - len(tested),
        "pct_complete": round(len(tested) / len(items) * 100, 1) if items else 0.0,
    }


@router.post("/{run_id}/evaluate", dependencies=[Depends(require_role("auditor"))])
async def evaluate(run_id: str, tolerable_misstatement: float, confidence_level: float = 0.95,
                    user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        items = list(result.scalars())

        tested_items = [i for i in items if i.audit_value is not None]
        untested_count = len(items) - len(tested_items)

        interval = (run.sample_manifest or {}).get("mus_selection_metadata", {}).get("sampling_interval")
        if interval is None:
            raise HTTPException(status_code=409, detail="run has no MUS sampling interval to evaluate against")

        import pandas as pd
        frame = pd.DataFrame([{
            "item_id": i.item_id, "_amount": float(i.amount), "audit_value": float(i.audit_value),
            "_selection_basis": i.selection_basis,
        } for i in tested_items])

        tested = tested_items_from_frame(frame) if len(frame) else []
        projection = project_misstatement(tested, sampling_interval=interval,
                                           confidence_level=confidence_level, tolerable_misstatement=tolerable_misstatement)
        workpaper = projection.as_workpaper()
        if untested_count:
            workpaper["warnings"].append(
                f"{untested_count} sample item(s) untested and excluded from the evaluation; "
                "they are not treated as clean."
            )

        evaluation = Evaluation(tenant_id=uuid.UUID(user.tenant_id), run_id=run.id, workpaper=workpaper,
                                 conclusion=projection.conclusion, created_by=uuid.UUID(user.user_id))
        session.add(evaluation)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="evaluation.created", subject=str(evaluation.id), payload={})
        evaluation_id = evaluation.id

    return {"evaluation_id": str(evaluation_id), "workpaper": workpaper}


@router.get("/{run_id}/evaluation")
async def get_evaluation(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(
            select(Evaluation).where(Evaluation.run_id == run.id).order_by(Evaluation.created_at.desc()).limit(1)
        )
        evaluation = result.scalar_one_or_none()
    if evaluation is None:
        raise HTTPException(status_code=404, detail="no evaluation exists for this run")
    return {"evaluation_id": str(evaluation.id), "workpaper": evaluation.workpaper, "conclusion": evaluation.conclusion,
            "signed_off_by": str(evaluation.signed_off_by) if evaluation.signed_off_by else None}


class SignOffRequest(BaseModel):
    evaluation_id: uuid.UUID


@router.post("/{run_id}/evaluation/sign-off", dependencies=[Depends(require_role("reviewer"))])
async def sign_off(run_id: str, req: SignOffRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        await _get_run_or_404(session, run_id)
        evaluation = await session.get(Evaluation, req.evaluation_id)
        if evaluation is None:
            raise HTTPException(status_code=404, detail="evaluation not found")

        evaluation.signed_off_by = uuid.UUID(user.user_id)
        evaluation.signed_off_at = datetime.now(UTC)
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="evaluation.signed_off",
                            subject=str(req.evaluation_id), payload={})

    return {"status": "signed_off"}
