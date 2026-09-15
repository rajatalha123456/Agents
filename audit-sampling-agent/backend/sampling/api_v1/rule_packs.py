"""RULE PACKS routes (section 6.1)."""
from __future__ import annotations

import datetime as dt
import uuid

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..auth.dependencies import CurrentUser, get_current_user, require_role
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import RulePackRow
from ..db.repositories import load_population
from ..db.session import tenant_session
from ..ingestion import add_risk_flags
from ..rules import Rule, RuleExpressionError, RulePack, evaluate_rules
from .pagination import Page, pagination_params

router = APIRouter(prefix="/api/v1/rule-packs", tags=["rule-packs"])


def _parse_rule_pack_yaml(yaml_source: str) -> RulePack:
    raw = yaml.safe_load(yaml_source)
    rules = []
    for r in raw["rules"]:
        rules.append(Rule(
            rule_id=r["rule_id"], description=r["description"], expression=r["expression"],
            severity=r["severity"], owner=r.get("owner", "unknown"), explanation=r.get("explanation", ""),
            effective_from=dt.date.fromisoformat(str(r["effective_from"])),
            effective_to=dt.date.fromisoformat(str(r["effective_to"])) if r.get("effective_to") else None,
            required_columns=tuple(r.get("required_columns", [])),
        ))
    return RulePack(pack_id=raw["pack_id"], pack_version=raw["pack_version"], rules=tuple(rules))


class RulePackOut(BaseModel):
    id: uuid.UUID
    pack_id: str
    pack_version: str
    owner: str | None
    approved_by: uuid.UUID | None


def _to_out(rp: RulePackRow) -> RulePackOut:
    return RulePackOut(id=rp.id, pack_id=rp.pack_id, pack_version=rp.pack_version, owner=rp.owner,
                        approved_by=rp.approved_by)


class RulePackCreate(BaseModel):
    yaml_source: str


@router.get("", response_model=Page[RulePackOut])
async def list_rule_packs(user: CurrentUser = Depends(get_current_user),
                           pagination: tuple[int, int] = Depends(pagination_params)) -> Page[RulePackOut]:
    limit, offset = pagination
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        total = (await session.execute(select(func.count()).select_from(RulePackRow))).scalar_one()
        result = await session.execute(select(RulePackRow).order_by(RulePackRow.created_at.desc()).limit(limit).offset(offset))
        rows = list(result.scalars())
    return Page(items=[_to_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=RulePackOut, dependencies=[Depends(require_role("auditor"))])
async def create_rule_pack(req: RulePackCreate, user: CurrentUser = Depends(get_current_user)) -> RulePackOut:
    try:
        pack = _parse_rule_pack_yaml(req.yaml_source)
    except (KeyError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid rule pack YAML: {exc}") from exc

    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        row = RulePackRow(tenant_id=uuid.UUID(user.tenant_id), pack_id=pack.pack_id, pack_version=pack.pack_version,
                           yaml_source=req.yaml_source, owner=user.user_id)
        session.add(row)
        await session.flush()
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="rule_pack.created", subject=str(row.id), payload={})
        result = _to_out(row)
    return result


@router.get("/{rule_pack_id}", response_model=RulePackOut)
async def get_rule_pack(rule_pack_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> RulePackOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        row = await session.get(RulePackRow, rule_pack_id)
    if row is None:
        raise HTTPException(status_code=404, detail="rule pack not found")
    return _to_out(row)


@router.post("/{rule_pack_id}/approve", response_model=RulePackOut, dependencies=[Depends(require_role("reviewer"))])
async def approve_rule_pack(rule_pack_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> RulePackOut:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        row = await session.get(RulePackRow, rule_pack_id)
        if row is None:
            raise HTTPException(status_code=404, detail="rule pack not found")

        import datetime as _dt
        row.approved_by = uuid.UUID(user.user_id)
        row.approved_at = _dt.datetime.now(_dt.UTC)
        trail = PgAuditTrail(user.tenant_id)
        await trail.append(session, actor=user.user_id, action="rule_pack.approved",
                            subject=str(rule_pack_id), payload={})
        result = _to_out(row)

    return result


class ValidateRequest(BaseModel):
    yaml_source: str


@router.post("/validate")
async def validate_rule_pack(req: ValidateRequest) -> dict:
    try:
        pack = _parse_rule_pack_yaml(req.yaml_source)
    except (KeyError, yaml.YAMLError) as exc:
        return {"valid": False, "errors": [str(exc)]}

    errors = []
    import pandas as pd
    dummy = pd.DataFrame({c: [] for c in ("amount", "approver_count", "posting_hour",
                                           "vendor_is_new", "vendor_transaction_count_30d")})
    for rule in pack.rules:
        try:
            from ..rules import evaluate_expression
            missing = [c for c in rule.required_columns if c not in dummy.columns]
            if not missing:
                evaluate_expression(rule.expression, dummy)
        except RuleExpressionError as exc:
            errors.append(f"rule '{rule.rule_id}': {exc}")

    return {"valid": not errors, "errors": errors, "pack_id": pack.pack_id, "pack_version": pack.pack_version,
            "rule_count": len(pack.rules)}


@router.post("/{rule_pack_id}/dry-run", dependencies=[Depends(require_role("auditor"))])
async def dry_run_rule_pack(rule_pack_id: uuid.UUID, dataset_id: uuid.UUID,
                             user: CurrentUser = Depends(get_current_user)) -> dict:
    async with tenant_session(uuid.UUID(user.tenant_id)) as session:
        row = await session.get(RulePackRow, rule_pack_id)
        if row is None:
            raise HTTPException(status_code=404, detail="rule pack not found")
        pack = _parse_rule_pack_yaml(row.yaml_source)

        frame = await load_population(session, dataset_id)

    flagged = add_risk_flags(frame)
    result = evaluate_rules(flagged, pack, as_of=dt.date.today())

    hit_counts = {rule.rule_id: int(result.fired[rule.rule_id].sum()) for rule in pack.in_force() if rule.rule_id not in result.skipped_rules}
    return {
        "pack_id": pack.pack_id, "pack_version": pack.pack_version,
        "population_size": len(flagged), "hit_counts": hit_counts,
        "skipped_rules": list(result.skipped_rules), "warnings": list(result.warnings),
    }
