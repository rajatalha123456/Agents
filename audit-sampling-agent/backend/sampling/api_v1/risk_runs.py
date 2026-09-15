"""RISK RUNS routes (section 6.1). Creation enqueues a job (202 + job id)
-- Phase 3's async processing, not a synchronous request-cycle sample.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.models import RiskRun, RiskScore, SampleItem
from ..db.session import tenant_session
from ..jobs.worker import enqueue_execute_risk_run
from .money import money_str
from .pagination import Page, pagination_params

router = APIRouter(prefix="/api/v1/risk-runs", tags=["risk-runs"])


class CreateRiskRunRequest(BaseModel):
    engagement_id: uuid.UUID
    dataset_id: uuid.UUID
    policy_id: uuid.UUID
    rule_pack_id: uuid.UUID | None = None
    user_seed: str | None = None
    as_of: dt.date | None = None
    run_id: str


class RiskRunOut(BaseModel):
    id: uuid.UUID
    run_id: str
    status: str
    progress_pct: int
    dataset_fingerprint: str | None
    error_message: str | None
    warnings: list | None
    risk_manifest: dict | None
    anomaly_manifest: dict | None
    rules_manifest: dict | None
    sample_manifest: dict | None


def _to_out(r: RiskRun) -> RiskRunOut:
    return RiskRunOut(
        id=r.id, run_id=r.run_id, status=r.status, progress_pct=r.progress_pct,
        dataset_fingerprint=r.dataset_fingerprint, error_message=r.error_message, warnings=r.warnings,
        risk_manifest=r.risk_manifest, anomaly_manifest=r.anomaly_manifest,
        rules_manifest=r.rules_manifest, sample_manifest=r.sample_manifest,
    )


@router.post("", status_code=202, dependencies=[Depends(require_role("auditor"))])
async def create_risk_run(req: CreateRiskRunRequest, response: Response,
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    tenant_id = uuid.UUID(user.tenant_id)
    async with tenant_session(tenant_id) as session:
        # dataset_fingerprint is authoritative once ingestion completes;
        # populate from the dataset row so load_population's later check
        # has something correct to compare against.
        from ..db.models import Dataset
        dataset = await session.get(Dataset, req.dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        if dataset.ingestion_status != "complete":
            raise HTTPException(status_code=409, detail=f"dataset ingestion status is '{dataset.ingestion_status}', not 'complete'")

        run = RiskRun(
            tenant_id=tenant_id, engagement_id=req.engagement_id, dataset_id=req.dataset_id,
            policy_id=req.policy_id, rule_pack_id=req.rule_pack_id, run_id=req.run_id,
            status="queued", user_seed=req.user_seed, as_of=req.as_of,
            dataset_fingerprint=dataset.dataset_fingerprint, created_by=uuid.UUID(user.user_id),
        )
        session.add(run)
        await session.flush()
        run_pk = run.id

    job_id = await enqueue_execute_risk_run(tenant_id, run_pk, actor=user.user_id)
    return {"run_id": req.run_id, "job_id": job_id, "status": "queued"}


@router.get("", response_model=Page[RiskRunOut])
async def list_risk_runs(user: CurrentUser = Depends(get_current_user),
                          pagination: tuple[int, int] = Depends(pagination_params)) -> Page[RiskRunOut]:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(RiskRun))).scalar_one()
        result = await session.execute(select(RiskRun).order_by(RiskRun.started_at.desc().nullslast()).limit(limit).offset(offset))
        rows = list(result.scalars())
    return Page(items=[_to_out(r) for r in rows], total=total, limit=limit, offset=offset)


async def _get_run_or_404(session, run_id: str) -> RiskRun:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}", response_model=RiskRunOut)
async def get_risk_run(run_id: str, user: CurrentUser = Depends(get_current_user)) -> RiskRunOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
    return _to_out(run)


@router.get("/{run_id}/transactions")
async def list_transactions(
    run_id: str, sort_by: str = "risk_score", stratum: str | None = None,
    user: CurrentUser = Depends(get_current_user), pagination: tuple[int, int] = Depends(pagination_params),
) -> dict:
    limit, offset = pagination
    if sort_by not in ("risk_score", "amount", "item_id"):
        raise HTTPException(status_code=422, detail="sort_by must be one of risk_score, amount, item_id")

    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)

        sample_result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        sample_by_item = {s.item_id: s for s in sample_result.scalars()}

        sort_col = {"risk_score": RiskScore.risk_score, "amount": RiskScore.amount, "item_id": RiskScore.item_id}[sort_by]
        query = select(RiskScore).where(RiskScore.run_id == run.id)
        if stratum:
            item_ids = [i for i, s in sample_by_item.items() if s.stratum == stratum]
            query = query.where(RiskScore.item_id.in_(item_ids))
        total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        query = query.order_by(sort_col.desc()).limit(limit).offset(offset)
        rows = list((await session.execute(query)).scalars())

    items = []
    for r in rows:
        sample = sample_by_item.get(r.item_id)
        items.append({
            "item_id": r.item_id, "amount": money_str(r.amount), "risk_score": float(r.risk_score) if r.risk_score is not None else None,
            "selected": sample is not None,
            "stratum": sample.stratum if sample else None,
            "selection_basis": sample.selection_basis if sample else None,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{run_id}/sample")
async def get_sample(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        items = list(result.scalars())

    return {
        "items": [
            {
                "item_id": i.item_id, "stratum": i.stratum, "selection_basis": i.selection_basis,
                "projectable": i.projectable, "amount": money_str(i.amount),
                "audit_value": money_str(i.audit_value),
            }
            for i in items
        ],
        "warnings": run.warnings,
    }


@router.get("/{run_id}/strata")
async def get_strata(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
        items = list(result.scalars())

    strata: dict[str, dict] = {}
    for i in items:
        s = strata.setdefault(i.stratum, {"projectable": i.projectable, "count": 0, "total_amount": 0.0})
        s["count"] += 1
        s["total_amount"] += float(i.amount or 0)

    for s in strata.values():
        s["total_amount"] = money_str(s["total_amount"])

    return {"strata": strata}


@router.post("/{run_id}/cancel", dependencies=[Depends(require_role("auditor"))])
async def cancel_run(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        if run.status not in ("queued", "running"):
            raise HTTPException(status_code=409, detail=f"cannot cancel a run in status '{run.status}'")
        run.status = "cancelled"
        run.completed_at = dt.datetime.now(dt.UTC)
    return {"status": "cancelled"}
