"""CHALLENGE routes (section 6.1): explanation, grounded narration,
comparison, and overrides.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..challenge import (
    OVERRIDE_AUDIT_ACTION,
    OVERRIDE_NOTE,
    ChallengeAction,
    build_evidence,
    build_override_payload,
    compare_items,
)
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Override, RiskRun, RiskScore, SampleItem, Tenant
from ..db.repositories import load_population
from ..db.session import tenant_session
from ..llm import LLMOrchestrator
from .llm_gate import DummyLLMClient, require_llm_enabled
from .rate_limit import rate_limit

router = APIRouter(prefix="/api/v1/risk-runs", tags=["challenge"])


@dataclass
class _MinimalSampleResult:
    items: pd.DataFrame


async def _get_run_or_404(session, run_id: str) -> RiskRun:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


async def _build_challenge_context(session, run: RiskRun):
    population = await load_population(session, run.dataset_id)

    sample_result_items = await session.execute(select(SampleItem).where(SampleItem.run_id == run.id))
    sample_rows = [
        {"item_id": i.item_id, "_amount": float(i.amount or 0), "_selection_basis": i.selection_basis}
        for i in sample_result_items.scalars()
    ]
    sample_result = _MinimalSampleResult(items=pd.DataFrame(sample_rows))

    interval = (run.sample_manifest or {}).get("mus_selection_metadata", {}).get("sampling_interval")
    high_risk_threshold = None  # policy-derived; omitted here since only the sample manifest is read

    scores_result = await session.execute(select(RiskScore).where(RiskScore.run_id == run.id))
    scores_by_item = {s.item_id: float(s.risk_score or 0) for s in scores_result.scalars()}

    @dataclass
    class _RiskResultShim:
        scores: dict

        def __getitem__(self, idx):
            return self.scores.get(idx, 0.0)

    population = population.reset_index(drop=True)
    risk_result = _RiskResultShim(scores={idx: scores_by_item.get(row["item_id"], 0.0) for idx, row in population.iterrows()})

    return population, sample_result, interval, high_risk_threshold, risk_result


@router.get("/{run_id}/items/{item_id}/explanation")
async def get_explanation(run_id: str, item_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        population, sample_result, interval, threshold, risk_result = await _build_challenge_context(session, run)
        evidence = build_evidence(item_id, population, sample_result, sampling_interval=interval,
                                   high_risk_threshold=threshold, risk_result=risk_result)
    return evidence.as_dict()


@router.post("/{run_id}/items/{item_id}/narrate",
             dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))])
async def narrate(run_id: str, item_id: str, question: str = "Why was this item selected or not selected?",
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
        require_llm_enabled(tenant)

        run = await _get_run_or_404(session, run_id)
        population, sample_result, interval, threshold, risk_result = await _build_challenge_context(session, run)
        evidence = build_evidence(item_id, population, sample_result, sampling_interval=interval,
                                   high_risk_threshold=threshold, risk_result=risk_result)

        orchestrator = LLMOrchestrator(DummyLLMClient(), model_identifier=tenant.llm_model or "stub", prompt_version="v1")
        result = orchestrator.narrate_challenge(question, evidence.as_dict())

    return result


@router.get("/{run_id}/compare")
async def compare(run_id: str, item_a: str, item_b: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        population, sample_result, interval, threshold, risk_result = await _build_challenge_context(session, run)
        return compare_items(item_a, item_b, population, sample_result, sampling_interval=interval,
                              high_risk_threshold=threshold, risk_result=risk_result)


class OverrideRequest(BaseModel):
    item_id: str
    action: str
    reason: str
    before_state: dict = {}
    after_state: dict = {}


@router.post("/{run_id}/override", dependencies=[Depends(require_role("auditor"))])
async def create_override(run_id: str, req: OverrideRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        action = ChallengeAction(req.action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown override action '{req.action}'") from exc

    # apply_override() in challenge.py is synchronous and calls
    # trail.append(actor=, action=, subject=, payload=) directly, assuming
    # the JSONL AuditTrail's sync call signature. PgAuditTrail.append() is
    # async and needs a bound session, so it can't be driven through that
    # function as-is. build_override_payload() is the same validation and
    # payload shape apply_override() uses internally (extracted so this
    # doesn't duplicate the reason-length rule or the payload shape by
    # hand); the actual write goes through PgAuditTrail directly.
    try:
        payload = build_override_payload(req.item_id, action, req.reason, req.before_state, req.after_state, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        trail = PgAuditTrail(user.tenant_id)
        event = await trail.append(session, actor=user.user_id, action=OVERRIDE_AUDIT_ACTION,
                                    subject=req.item_id, payload=payload)

        override = Override(
            tenant_id=uuid.UUID(user.tenant_id), run_id=run.id, item_id=req.item_id, action=action.value,
            reason=req.reason, before_state=req.before_state, after_state=req.after_state,
            audit_event_hash=event.event_hash, created_by=uuid.UUID(user.user_id),
        )
        session.add(override)
        await session.flush()
        result = {"override_id": str(override.id), "note": OVERRIDE_NOTE}
    return result


@router.get("/{run_id}/overrides")
async def list_overrides(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await _get_run_or_404(session, run_id)
        result = await session.execute(select(Override).where(Override.run_id == run.id))
        overrides = list(result.scalars())
    return {
        "items": [
            {"id": str(o.id), "item_id": o.item_id, "action": o.action, "reason": o.reason,
             "approved_by": str(o.approved_by) if o.approved_by else None}
            for o in overrides
        ],
    }
