"""Creates the single default tenant/user this no-login deployment runs as.

Idempotent: safe to call on every startup. See auth/dependencies.py for
DEFAULT_TENANT_ID / DEFAULT_USER_ID, which this must stay in sync with.
"""
from __future__ import annotations

from sqlalchemy import select

from .auth.dependencies import DEFAULT_TENANT_ID, DEFAULT_USER_ID
from .auth.passwords import hash_password
from .db.models import Tenant, User
from .db.session import login_session, tenant_session


async def ensure_default_tenant_user() -> None:
    async with login_session() as session:
        tenant = await session.get(Tenant, DEFAULT_TENANT_ID)
        if tenant is None:
            session.add(Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default"))

    async with tenant_session(DEFAULT_TENANT_ID) as session:
        user = (
            await session.execute(select(User).where(User.id == DEFAULT_USER_ID))
        ).scalar_one_or_none()
        if user is None:
            session.add(
                User(
                    id=DEFAULT_USER_ID,
                    tenant_id=DEFAULT_TENANT_ID,
                    email="default@local",
                    full_name="Default User",
                    password_hash=hash_password("unused-no-login"),
                    role="admin",
                )
            )
