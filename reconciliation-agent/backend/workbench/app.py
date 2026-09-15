"""Loopback-only evaluation API. Run with uvicorn workbench.app:app.

This is explicitly a single-user local sandbox with selectable simulation
roles. It must not be deployed as the production multi-tenant API.
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from core.audit.chain import ChainableEvent, verify_chain
from core.ingestion.parsers.base import ParseError
from core.packs.loader import load_pack_file
from workbench import service
from workbench.auth import AuthError, authenticate, create_token, decode_token
from workbench.store import Store


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class PeriodInput(BaseModel):
    period: str

    @field_validator("period")
    @classmethod
    def valid_period(cls, value):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            raise ValueError("Use YYYY-MM for period.")
        return value


class ImportInput(PeriodInput):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=2_000_000)
    side: Literal["SOURCE_A", "SOURCE_B"]
    account: str = Field(min_length=1, max_length=100)
    field_map: dict[str, str] | None = None
    expected_row_count: int | None = Field(default=None, ge=0)
    file_format: Literal["CSV", "MT940", "CAMT053", "EXCEL", "BAI2"] = "CSV"


class DecisionInput(BaseModel):
    action: Literal["APPROVE", "REJECT", "RETURN", "CLOSE", "REOPEN"]
    reason: str = Field(min_length=3, max_length=2000)
    external_ref: str | None = Field(default=None, max_length=300)


class JournalLineInput(BaseModel):
    side: Literal["DR", "CR"]
    account_role: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=40)


class JournalDraftInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=100)
    lines: list[JournalLineInput] = Field(min_length=2, max_length=20)
    reason: str = Field(min_length=3, max_length=2000)


class JournalDraftDecisionInput(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3, max_length=2000)


class CertificationInput(PeriodInput):
    reason: str = Field(min_length=3, max_length=2000)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ManualMatchInput(BaseModel):
    record_ids: list[str] = Field(min_length=2, max_length=50)
    reason: str = Field(min_length=3, max_length=2000)


def create_app(path=None):
    app = FastAPI(title="Reconcile local evaluation API", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    store = Store(path or os.getenv("RECON_WORKBENCH_DB", str(Path(__file__).resolve().parents[2] / ".data" / "workbench.sqlite3")))
    app.state.store = store

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        if request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
            return JSONResponse({"detail": "This evaluation API only accepts loopback connections."}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed_origins = os.getenv("RECON_ALLOWED_ORIGINS", "http://127.0.0.1:5178,http://localhost:5178,http://127.0.0.1:8765,http://localhost:8765").split(",")
            if origin and origin not in allowed_origins:
                return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)
            if request.headers.get("x-workspace-client") != "reconcile-local":
                return JSONResponse({"detail": "Local workspace client header is required."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    @app.exception_handler(ParseError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    def require_actor(authorization: str | None) -> str:
        """Every mutating route derives the acting user from a verified JWT,
        never from a client-supplied name — the token's signature is the
        only thing that establishes identity here.
        """
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Sign in required.")
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = decode_token(token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if claims.username not in service.ACTORS:
            raise HTTPException(status_code=401, detail="Unknown session identity.")
        return claims.username

    def mutate(fn, authorization, *args, **kwargs):
        actor = require_actor(authorization)
        with store.transaction() as state:
            return fn(state, actor, *args, **kwargs)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "LOCAL_EVALUATION", "authenticated": False}

    @app.post("/api/auth/login")
    def login(body: LoginInput):
        state = store.read()
        try:
            user = authenticate(state["users"], body.username, body.password)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        token = create_token(username=user["username"], role=user["role"], display_name=user["display_name"])
        return {"access_token": token, "token_type": "bearer", "actor": user["username"], "role": user["role"], "display_name": user["display_name"]}

    @app.get("/api/workspace")
    def workspace(authorization: str | None = Header(default=None)):
        require_actor(authorization)
        state = store.read()
        state.pop("users", None)
        state["mode"] = "LOCAL_EVALUATION"
        state["audit_valid"] = not verify_chain([ChainableEvent(**{**e, "created_at": datetime.fromisoformat(e["created_at"])}) for e in state["audit"]])
        return state

    @app.post("/api/sample")
    def sample(authorization: str | None = Header(default=None)):
        return mutate(service.seed, authorization)

    @app.post("/api/imports")
    def imports(body: ImportInput, authorization: str | None = Header(default=None)):
        return mutate(service.import_csv, authorization, **body.model_dump())

    @app.post("/api/reconcile")
    def reconcile(body: PeriodInput, authorization: str | None = Header(default=None)):
        return mutate(service.reconcile, authorization, body.period)

    @app.post("/api/check")
    def check_records(body: PeriodInput, authorization: str | None = Header(default=None)):
        return mutate(service.check_records, authorization, body.period)

    @app.post("/api/matches/manual")
    def create_manual_match(body: ManualMatchInput, authorization: str | None = Header(default=None)):
        return mutate(service.create_manual_match, authorization, body.record_ids, body.reason)

    @app.post("/api/matches/{match_id}/unmatch")
    def unmatch(match_id: str, body: ReasonInput, authorization: str | None = Header(default=None)):
        return mutate(service.unmatch, authorization, match_id, body.reason)

    @app.post("/api/imports/{batch_id}/reject")
    def reject_import(batch_id: str, body: ReasonInput, authorization: str | None = Header(default=None)):
        return mutate(service.reject_import, authorization, batch_id, body.reason)

    @app.post("/api/agent-runs")
    def triage(body: PeriodInput, authorization: str | None = Header(default=None)):
        return mutate(service.triage, authorization, body.period)

    @app.post("/api/breaks/{case_id}/decisions")
    def decide(case_id: str, body: DecisionInput, authorization: str | None = Header(default=None)):
        return mutate(service.decide, authorization, case_id, **body.model_dump())

    @app.post("/api/journal-drafts")
    def create_journal_draft(body: JournalDraftInput, authorization: str | None = Header(default=None)):
        return mutate(service.create_journal_draft, authorization, body.case_id, [line.model_dump() for line in body.lines], body.reason)

    @app.post("/api/journal-drafts/{draft_id}/decisions")
    def decide_journal_draft(draft_id: str, body: JournalDraftDecisionInput, authorization: str | None = Header(default=None)):
        return mutate(service.decide_journal_draft, authorization, draft_id, **body.model_dump())

    @app.post("/api/certify")
    def certify(body: CertificationInput, authorization: str | None = Header(default=None)):
        return mutate(service.certify, authorization, **body.model_dump())

    @app.get("/api/packs")
    def packs():
        manifest = load_pack_file(Path(__file__).resolve().parents[1] / "packs" / "core" / "manifest.yaml")
        return manifest.model_dump(mode="json")

    @app.get("/api/admin-config")
    def admin_config():
        return service.admin_config_snapshot()

    @app.get("/api/model-governance")
    def model_governance():
        return service.mock_data.model_governance_snapshot()

    @app.get("/api/pilot")
    def pilot(authorization: str | None = Header(default=None)):
        require_actor(authorization)
        return service.mock_data.pilot_tenant_snapshot(store.read())

    @app.get("/api/export")
    def export(authorization: str | None = Header(default=None)):
        require_actor(authorization)
        state = store.read()
        state.pop("users", None)
        import hashlib
        import json
        payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
        return JSONResponse({"manifest": {"mode": "LOCAL_EVALUATION", "sha256": hashlib.sha256(payload.encode()).hexdigest(), "created_at": service.now()}, "workspace": state}, headers={"Content-Disposition": 'attachment; filename="reconciliation-evidence.json"'})

    return app


app = create_app()
