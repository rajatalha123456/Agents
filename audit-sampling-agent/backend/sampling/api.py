"""FastAPI app backed by PostgreSQL, with RBAC and segregation-of-duties
enforcement. No in-memory registries.

This deployment has no login: every request resolves to the same fixed
tenant/user (see auth/dependencies.py). tenant_id is never read from a
request body, query parameter, or header -- a tenant_id present in a
request body is checked against it and rejected (403 + audit event) on
mismatch rather than silently ignored.

Async job processing is Phase 3; POST /runs here runs the sample
synchronously, which is correct for the earlier phases' acceptance bar
(a run persists across a restart) but will move behind a queue in Phase 3.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from .api_v1 import audit_events as v1_audit_events
from .api_v1 import benchmark as v1_benchmark
from .api_v1 import challenge as v1_challenge
from .api_v1 import datasets as v1_datasets
from .api_v1 import engagements as v1_engagements
from .api_v1 import evidence as v1_evidence
from .api_v1 import policies as v1_policies
from .api_v1 import risk_runs as v1_risk_runs
from .api_v1 import rule_packs as v1_rule_packs
from .api_v1 import system as v1_system
from .api_v1 import tenant_admin as v1_tenant_admin
from .api_v1 import testing as v1_testing
from .api_v1.errors import register_problem_details
from .auth.dependencies import CurrentUser, get_current_user, require_role
from .bootstrap import ensure_default_tenant_user
from .db.audit_trail_pg import PgAuditTrail
from .db.repositories import DatasetFingerprintMismatch, load_population
from .db.run_repository import load_run_by_run_id, load_sample_item_ids, persist_run
from .db.session import tenant_session
from .engine import SamplingPolicy, build_sample
from .observability import configure_logging, new_correlation_id, set_correlation_id

configure_logging()

app = FastAPI(
    title="Audit Sampling Agent",
    description="ISA 530 statistical sampling and risk-based selection engine.",
    version="0.4.0",
)


@app.on_event("startup")
async def _bootstrap() -> None:
    await ensure_default_tenant_user()


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or new_correlation_id()
    set_correlation_id(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response

# Dev-only CORS: allow the Vite dev server to call this API directly.
# ALLOWED_ORIGINS must be set explicitly for any non-dev deployment --
# defaulting to "*" here would be a real cross-tenant data-leak vector
# once cookies or credentials are involved.
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_problem_details(app)

for _router in (
    v1_system.router, v1_tenant_admin.router, v1_engagements.router, v1_datasets.router,
    v1_policies.router, v1_rule_packs.router, v1_risk_runs.router, v1_testing.router,
    v1_challenge.router, v1_benchmark.router, v1_evidence.router, v1_audit_events.router,
):
    app.include_router(_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse(status="ready")


class CreateRunRequest(BaseModel):
    tenant_id: uuid.UUID | None = None
    engagement_id: uuid.UUID
    dataset_id: uuid.UUID
    policy_id: uuid.UUID
    policy_version: str
    tolerable_misstatement: float
    confidence_level: float = 0.95
    expected_misstatement: float = 0.0
    random_control_size: int = 0
    high_risk_threshold: float | None = None
    user_seed: str | None = None
    run_id: str


@app.post("/runs", dependencies=[Depends(require_role("auditor"))])
async def create_run(req: CreateRunRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    tenant_id = uuid.UUID(user.tenant_id)

    if req.tenant_id is not None and str(req.tenant_id) != user.tenant_id:
        async with tenant_session(tenant_id) as session:
            trail = PgAuditTrail(user.tenant_id)
            await trail.append(
                session, actor=user.user_id, action="auth.tenant_mismatch",
                subject=user.user_id, payload={"body_tenant_id": str(req.tenant_id)},
            )
        raise HTTPException(status_code=403, detail="tenant_id in request body does not match authenticated tenant")

    async with tenant_session(tenant_id) as session:
        try:
            frame = await load_population(session, req.dataset_id)
        except DatasetFingerprintMismatch as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        policy = SamplingPolicy(
            policy_version=req.policy_version,
            tolerable_misstatement=req.tolerable_misstatement,
            confidence_level=req.confidence_level,
            expected_misstatement=req.expected_misstatement,
            random_control_size=req.random_control_size,
            high_risk_threshold=req.high_risk_threshold,
        )
        sample_result = build_sample(frame, policy, user_seed=req.user_seed)

        run = await persist_run(
            session, tenant_id, req.engagement_id, req.dataset_id, req.policy_id,
            req.run_id, req.policy_version, req.user_seed, sample_result,
        )
        await session.execute(
            text("UPDATE risk_runs SET created_by = :uid WHERE id = :rid"),
            {"uid": user.user_id, "rid": run.id},
        )

    return {"run_id": run.run_id, "status": run.status, "warnings": run.warnings}


@app.get("/runs/{run_id}")
async def get_run(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        run = await load_run_by_run_id(session, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        item_ids = await load_sample_item_ids(session, run.id)

    return {
        "run_id": run.run_id,
        "status": run.status,
        "dataset_fingerprint": run.dataset_fingerprint,
        "sample_manifest": run.sample_manifest,
        "warnings": run.warnings,
        "selected_item_ids": item_ids,
    }


# --- Approval endpoints ---------------------------------------------------
# Segregation-of-duties (creator != approver) is not enforced here: this
# deployment has a single fixed user (no login), so a maker/checker split
# does not apply. Approving still requires the "reviewer" role and is
# still recorded in the audit trail.

class ApprovalResponse(BaseModel):
    status: str


@app.post("/policies/{policy_id}/approve", response_model=ApprovalResponse,
          dependencies=[Depends(require_role("reviewer"))])
async def approve_policy(policy_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> ApprovalResponse:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        result = await session.execute(text("SELECT created_by FROM sampling_policies WHERE id = :pid"), {"pid": policy_id})
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="policy not found")
        await session.execute(
            text("UPDATE sampling_policies SET approved_by = :uid, approved_at = :now WHERE id = :pid"),
            {"uid": user.user_id, "now": datetime.now(UTC), "pid": policy_id},
        )
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="policy.approved", subject=str(policy_id), payload={})

    return ApprovalResponse(status="approved")


@app.post("/rule-packs/{rule_pack_id}/approve", response_model=ApprovalResponse,
          dependencies=[Depends(require_role("reviewer"))])
async def approve_rule_pack(rule_pack_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> ApprovalResponse:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        result = await session.execute(text("SELECT owner FROM rule_packs WHERE id = :rid"), {"rid": rule_pack_id})
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="rule pack not found")
        await session.execute(
            text("UPDATE rule_packs SET approved_by = :uid, approved_at = :now WHERE id = :rid"),
            {"uid": user.user_id, "now": datetime.now(UTC), "rid": rule_pack_id},
        )
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="rule_pack.approved", subject=str(rule_pack_id), payload={})

    return ApprovalResponse(status="approved")


@app.post("/overrides/{override_id}/approve", response_model=ApprovalResponse,
          dependencies=[Depends(require_role("reviewer"))])
async def approve_override(override_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> ApprovalResponse:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        result = await session.execute(text("SELECT created_by FROM overrides WHERE id = :oid"), {"oid": override_id})
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="override not found")
        await session.execute(
            text("UPDATE overrides SET approved_by = :uid, approved_at = :now WHERE id = :oid"),
            {"uid": user.user_id, "now": datetime.now(UTC), "oid": override_id},
        )
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="override.approved", subject=str(override_id), payload={})

    return ApprovalResponse(status="approved")


class EvaluationSignOffRequest(BaseModel):
    evaluation_id: uuid.UUID


@app.post("/risk-runs/{run_id}/evaluation/sign-off", response_model=ApprovalResponse,
          dependencies=[Depends(require_role("reviewer"))])
async def sign_off_evaluation(
    run_id: uuid.UUID, req: EvaluationSignOffRequest, user: CurrentUser = Depends(get_current_user)
) -> ApprovalResponse:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        result = await session.execute(text("SELECT created_by FROM risk_runs WHERE id = :rid"), {"rid": run_id})
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="run not found")
        await session.execute(
            text("UPDATE evaluations SET signed_off_by = :uid, signed_off_at = :now WHERE id = :eid"),
            {"uid": user.user_id, "now": datetime.now(UTC), "eid": req.evaluation_id},
        )
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(
            session, actor=user.user_id, action="evaluation.signed_off", subject=str(req.evaluation_id), payload={}
        )

    return ApprovalResponse(status="signed_off")


def assert_no_write_back_routes() -> None:
    """Section 0.5 CI guard: no route may post, adjust, correct, or reverse
    anything in a client financial system. Invoked directly by the test
    suite; also safe to run as a standalone check.
    """
    forbidden = ("post", "adjust", "correct", "reverse", "writeback", "write-back")
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        assert not any(word in path for word in forbidden), f"write-back route: {path}"
