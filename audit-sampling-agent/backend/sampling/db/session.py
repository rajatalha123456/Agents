"""Async engine/session setup, connecting as app_role (no BYPASSRLS).

Tenant context is set per-transaction via set_config(..., true) -- never
session-level -- so it cannot leak to a different request that later
borrows the same pooled connection.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

APP_DATABASE_URL = os.environ.get(
    "APP_DATABASE_URL",
    "postgresql+asyncpg://app_role:app_role_dev_password@localhost:55433/audit_sampling",
)

engine = create_async_engine(APP_DATABASE_URL, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def login_session():
    """A session with no app.tenant_id set, for the narrow pre-authentication
    lookups (login, refresh-token tenant discovery) that run through a
    SECURITY DEFINER function rather than through RLS-protected tables
    directly. Never use this for anything else.
    """
    async with SessionFactory() as session:
        async with session.begin():
            yield session


@asynccontextmanager
async def tenant_session(tenant_id: uuid.UUID | str):
    """Yield a session with app.tenant_id set for this transaction only.

    The third argument to set_config (`true`) makes the setting
    transaction-local. Using session-level config here would leak the
    tenant to whatever request next borrows this pooled connection --
    a cross-tenant data leak.
    """
    async with SessionFactory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session
