"""FastAPI dependency for the current user.

Login/JWT is intentionally removed: this agent runs single-user, so every
request resolves to the same fixed tenant/user (see DEFAULT_TENANT_ID,
DEFAULT_USER_ID). tenant_id is never read from a request body, query
parameter, or header -- see the note on tenant_id_conflict below.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from ..db.audit_trail_pg import PgAuditTrail
from ..db.session import tenant_session

# Fixed for the life of this deployment -- see bootstrap.ensure_default_tenant_user,
# which creates the matching rows in the database on startup.
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

ROLE_RANK = {"viewer": 0, "auditor": 1, "reviewer": 2, "admin": 3}


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    role: str


async def get_current_user() -> CurrentUser:
    return CurrentUser(user_id=str(DEFAULT_USER_ID), tenant_id=str(DEFAULT_TENANT_ID), role="admin")


def require_role(minimum_role: str):
    """Role hierarchy: viewer < auditor < reviewer < admin. A dependency,
    not a scattered in-handler check, so every protected route declares
    its requirement in one visible place.
    """
    minimum_rank = ROLE_RANK[minimum_role]

    async def _dependency(request: Request, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if ROLE_RANK.get(user.role, -1) < minimum_rank:
            detail = f"requires role '{minimum_role}' or higher; caller has '{user.role}'"
            async with tenant_session(uuid.UUID(user.tenant_id)) as session:
                trail = PgAuditTrail(user.tenant_id)
                await trail.append(
                    session, actor=user.user_id, action="auth.permission_denied",
                    subject=request.url.path, payload={"required_role": minimum_role, "actual_role": user.role},
                )
            raise HTTPException(status_code=403, detail=detail)
        return user

    return _dependency
