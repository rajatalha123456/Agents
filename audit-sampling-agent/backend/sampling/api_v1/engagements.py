"""ENGAGEMENTS routes (section 6.1)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Engagement
from ..db.session import tenant_session
from .money import money_str
from .pagination import Page, pagination_params

router = APIRouter(prefix="/api/v1/engagements", tags=["engagements"])


class EngagementOut(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str
    period_start: dt.date | None
    period_end: dt.date | None
    status: str
    performance_materiality: str | None


class EngagementCreate(BaseModel):
    name: str
    client_name: str
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    performance_materiality: float | None = None


class EngagementPatch(BaseModel):
    name: str | None = None
    status: str | None = None
    performance_materiality: float | None = None


def _to_out(e: Engagement) -> EngagementOut:
    return EngagementOut(
        id=e.id, name=e.name, client_name=e.client_name, period_start=e.period_start,
        period_end=e.period_end, status=e.status, performance_materiality=money_str(e.performance_materiality),
    )


@router.get("", response_model=Page[EngagementOut])
async def list_engagements(user: CurrentUser = Depends(get_current_user),
                            pagination: tuple[int, int] = Depends(pagination_params)) -> Page[EngagementOut]:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(Engagement))).scalar_one()
        result = await session.execute(select(Engagement).order_by(Engagement.created_at.desc()).limit(limit).offset(offset))
        rows = list(result.scalars())
    return Page(items=[_to_out(e) for e in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=EngagementOut, dependencies=[Depends(require_role("auditor"))])
async def create_engagement(req: EngagementCreate, user: CurrentUser = Depends(get_current_user)) -> EngagementOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        engagement = Engagement(
            tenant_id=uuid.UUID(user.tenant_id), name=req.name, client_name=req.client_name,
            period_start=req.period_start, period_end=req.period_end,
            performance_materiality=req.performance_materiality, created_by=uuid.UUID(user.user_id),
        )
        session.add(engagement)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="engagement.created", subject=str(engagement.id), payload={})
        result = _to_out(engagement)
    return result


@router.get("/{engagement_id}", response_model=EngagementOut)
async def get_engagement(engagement_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> EngagementOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        engagement = await session.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return _to_out(engagement)


@router.patch("/{engagement_id}", response_model=EngagementOut, dependencies=[Depends(require_role("auditor"))])
async def patch_engagement(engagement_id: uuid.UUID, patch: EngagementPatch,
                            user: CurrentUser = Depends(get_current_user)) -> EngagementOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        engagement = await session.get(Engagement, engagement_id)
        if engagement is None:
            raise HTTPException(status_code=404, detail="engagement not found")
        if patch.name is not None:
            engagement.name = patch.name
        if patch.status is not None:
            engagement.status = patch.status
        if patch.performance_materiality is not None:
            engagement.performance_materiality = patch.performance_materiality
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="engagement.updated",
                            subject=str(engagement_id), payload=patch.model_dump(exclude_none=True))
        result = _to_out(engagement)
    return result
