"""POLICIES routes (section 6.1)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import SamplingPolicyRow
from ..db.session import tenant_session
from ..statistics import SampleSizeResult, mus_sample_size
from .money import money_str
from .pagination import Page, pagination_params

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


class PolicyOut(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    policy_version: str
    tolerable_misstatement: str | None
    confidence_level: float | None
    approved_by: uuid.UUID | None


class PolicyCreate(BaseModel):
    engagement_id: uuid.UUID
    policy_version: str
    tolerable_misstatement: float
    confidence_level: float = 0.95
    expected_misstatement: float = 0.0
    min_sample_size: int = 0
    max_sample_size: int | None = None
    high_risk_threshold: float | None = None
    high_risk_top_n: int | None = None
    random_control_size: int = 0
    test_negative_balances_100pct: bool = True
    review_zero_balances: bool = False


def _to_out(p: SamplingPolicyRow) -> PolicyOut:
    return PolicyOut(
        id=p.id, engagement_id=p.engagement_id, policy_version=p.policy_version,
        tolerable_misstatement=money_str(p.tolerable_misstatement),
        confidence_level=float(p.confidence_level) if p.confidence_level else None,
        approved_by=p.approved_by,
    )


@router.get("", response_model=Page[PolicyOut])
async def list_policies(user: CurrentUser = Depends(get_current_user),
                         pagination: tuple[int, int] = Depends(pagination_params)) -> Page[PolicyOut]:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(SamplingPolicyRow))).scalar_one()
        result = await session.execute(
            select(SamplingPolicyRow).order_by(SamplingPolicyRow.created_at.desc()).limit(limit).offset(offset)
        )
        rows = list(result.scalars())
    return Page(items=[_to_out(p) for p in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=PolicyOut, dependencies=[Depends(require_role("auditor"))])
async def create_policy(req: PolicyCreate, user: CurrentUser = Depends(get_current_user)) -> PolicyOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        policy = SamplingPolicyRow(tenant_id=uuid.UUID(user.tenant_id), created_by=uuid.UUID(user.user_id),
                                    **req.model_dump())
        session.add(policy)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="policy.created", subject=str(policy.id), payload={})
        result = _to_out(policy)
    return result


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(policy_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> PolicyOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        policy = await session.get(SamplingPolicyRow, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="policy not found")
    return _to_out(policy)


@router.post("/{policy_id}/approve", response_model=PolicyOut, dependencies=[Depends(require_role("reviewer"))])
async def approve_policy(policy_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> PolicyOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        policy = await session.get(SamplingPolicyRow, policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="policy not found")

        policy.approved_by = uuid.UUID(user.user_id)
        policy.approved_at = datetime.now(UTC)
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="policy.approved",
                            subject=str(policy_id), payload={})
        result = _to_out(policy)

    return result


class SampleSizePreviewRequest(BaseModel):
    book_value: float
    tolerable_misstatement: float
    expected_misstatement: float = 0.0
    confidence_level: float = 0.95
    min_sample_size: int = 0
    max_sample_size: int | None = None


@router.post("/preview-sample-size")
async def preview_sample_size(req: SampleSizePreviewRequest) -> dict:
    try:
        result: SampleSizeResult = mus_sample_size(
            book_value=req.book_value, tolerable_misstatement=req.tolerable_misstatement,
            expected_misstatement=req.expected_misstatement, confidence_level=req.confidence_level,
            min_sample_size=req.min_sample_size, max_sample_size=req.max_sample_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.as_workpaper()
