"""TENANT ADMIN routes (section 6.1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..auth.passwords import hash_password
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Tenant, User
from ..db.session import tenant_session
from .pagination import Page, pagination_params

router = APIRouter(prefix="/api/v1/tenant", tags=["tenant"])


class TenantSettings(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    data_residency_region: str
    llm_enabled: bool
    llm_provider: str | None
    llm_model: str | None


class TenantPatch(BaseModel):
    name: str | None = None
    data_residency_region: str | None = None


@router.get("", response_model=TenantSettings)
async def get_tenant(user: CurrentUser = Depends(get_current_user)) -> TenantSettings:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return TenantSettings(
        id=tenant.id, name=tenant.name, slug=tenant.slug,
        data_residency_region=tenant.data_residency_region,
        llm_enabled=tenant.llm_enabled, llm_provider=tenant.llm_provider, llm_model=tenant.llm_model,
    )


@router.patch("", response_model=TenantSettings, dependencies=[Depends(require_role("admin"))])
async def patch_tenant(patch: TenantPatch, user: CurrentUser = Depends(get_current_user)) -> TenantSettings:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
        if patch.name is not None:
            tenant.name = patch.name
        if patch.data_residency_region is not None:
            tenant.data_residency_region = patch.data_residency_region
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="tenant.settings_updated",
                            subject=user.tenant_id, payload=patch.model_dump(exclude_none=True))
        result = TenantSettings(
            id=tenant.id, name=tenant.name, slug=tenant.slug,
            data_residency_region=tenant.data_residency_region,
            llm_enabled=tenant.llm_enabled, llm_provider=tenant.llm_provider, llm_model=tenant.llm_model,
        )
    return result


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool


class InviteUserRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: str
    temporary_password: str


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.get("/users", response_model=Page[UserOut], dependencies=[Depends(require_role("admin"))])
async def list_users(user: CurrentUser = Depends(get_current_user),
                      pagination: tuple[int, int] = Depends(pagination_params)) -> Page[UserOut]:
    limit, offset = pagination
    from sqlalchemy import func, select
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        result = await session.execute(select(User).order_by(User.created_at).limit(limit).offset(offset))
        users = list(result.scalars())
    return Page(
        items=[UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role, is_active=u.is_active) for u in users],
        total=total, limit=limit, offset=offset,
    )


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_role("admin"))])
async def invite_user(req: InviteUserRequest, user: CurrentUser = Depends(get_current_user)) -> UserOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        new_user = User(
            tenant_id=uuid.UUID(user.tenant_id), email=req.email, full_name=req.full_name,
            password_hash=hash_password(req.temporary_password), role=req.role,
        )
        session.add(new_user)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="tenant.user_invited",
                            subject=str(new_user.id), payload={"email": req.email, "role": req.role})
        result = UserOut(id=new_user.id, email=new_user.email, full_name=new_user.full_name,
                          role=new_user.role, is_active=new_user.is_active)
    return result


@router.patch("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_role("admin"))])
async def patch_user(user_id: uuid.UUID, patch: UserPatch, user: CurrentUser = Depends(get_current_user)) -> UserOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        target = await session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="user not found")
        if patch.role is not None:
            target.role = patch.role
        if patch.is_active is not None:
            target.is_active = patch.is_active
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="tenant.user_updated",
                            subject=str(user_id), payload=patch.model_dump(exclude_none=True))
        result = UserOut(id=target.id, email=target.email, full_name=target.full_name,
                          role=target.role, is_active=target.is_active)
    return result


class LLMConfig(BaseModel):
    llm_enabled: bool
    llm_provider: str | None
    llm_model: str | None


@router.get("/llm-config", response_model=LLMConfig)
async def get_llm_config(user: CurrentUser = Depends(get_current_user)) -> LLMConfig:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
    return LLMConfig(llm_enabled=tenant.llm_enabled, llm_provider=tenant.llm_provider, llm_model=tenant.llm_model)


@router.put("/llm-config", response_model=LLMConfig, dependencies=[Depends(require_role("admin"))])
async def put_llm_config(config: LLMConfig, user: CurrentUser = Depends(get_current_user)) -> LLMConfig:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        tenant = await session.get(Tenant, uuid.UUID(user.tenant_id))
        tenant.llm_enabled = config.llm_enabled
        tenant.llm_provider = config.llm_provider
        tenant.llm_model = config.llm_model
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="tenant.llm_config_updated",
                            subject=user.tenant_id, payload=config.model_dump())
    return config
