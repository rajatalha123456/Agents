"""AUDIT TRAIL routes (section 6.1)."""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..auth.dependencies import CurrentUser, get_current_user
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import AuditEventRow
from ..db.session import tenant_session
from .pagination import pagination_params

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit-trail"])


@router.get("")
async def list_audit_events(
    subject: str | None = None, actor: str | None = None, action: str | None = None,
    user: CurrentUser = Depends(get_current_user), pagination: tuple[int, int] = Depends(pagination_params),
) -> dict:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        query = select(AuditEventRow).where(AuditEventRow.tenant_id == uuid.UUID(user.tenant_id))
        if subject:
            query = query.where(AuditEventRow.subject == subject)
        if actor:
            query = query.where(AuditEventRow.actor == actor)
        if action:
            query = query.where(AuditEventRow.action == action)

        from sqlalchemy import func
        total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        query = query.order_by(AuditEventRow.sequence.desc()).limit(limit).offset(offset)
        rows = list((await session.execute(query)).scalars())

    return {
        "items": [
            {"sequence": r.sequence, "timestamp": r.timestamp.isoformat(), "actor": r.actor,
             "action": r.action, "subject": r.subject, "payload": r.payload}
            for r in rows
        ],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/verify")
async def verify_audit_trail(user: CurrentUser = Depends(get_current_user)) -> dict:
    trail = PgAuditTrail(uuid.UUID(user.tenant_id))
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        report = await trail.verify(session)
    return {"valid": report.valid, "first_invalid_sequence": report.first_invalid_sequence,
            "reason": report.reason, "events_checked": report.events_checked}


@router.get("/export")
async def export_audit_trail(user: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    trail = PgAuditTrail(uuid.UUID(user.tenant_id))
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        events = await trail.events(session)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["sequence", "timestamp", "actor", "action", "subject", "event_hash"])
    for e in events:
        writer.writerow([e.sequence, e.timestamp, e.actor, e.action, e.subject, e.event_hash])
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=audit_trail_export.csv"})
