"""anchor_audit_trail job: nightly head-hash anchor per tenant.

Writes the current chain head to audit_anchors. Pushing that anchor to
append-only external storage (S3 Object Lock or equivalent) is a Phase 6
infrastructure concern; the hook is left explicit below rather than
silently omitted.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import AuditAnchor, Tenant
from ..db.session import SessionFactory, tenant_session


async def anchor_audit_trail(tenant_id: uuid.UUID) -> dict:
    trail = PgAuditTrail(tenant_id)
    async with tenant_session(tenant_id) as session:
        head = await trail.head(session)
        anchor = AuditAnchor(
            tenant_id=tenant_id,
            head_sequence=head.sequence if head else None,
            head_hash=head.event_hash if head else None,
            external_reference=None,  # TODO(Phase 6): push to S3 Object Lock / equivalent
        )
        session.add(anchor)
        await session.flush()
        anchor_id = anchor.id

    return {"anchor_id": str(anchor_id), "head_sequence": head.sequence if head else None}


async def anchor_audit_trail_all_tenants() -> dict[str, dict]:
    async with SessionFactory() as session:
        result = await session.execute(select(Tenant.id))
        tenant_ids = [r[0] for r in result]

    results = {}
    for tenant_id in tenant_ids:
        results[str(tenant_id)] = await anchor_audit_trail(tenant_id)
    return results
