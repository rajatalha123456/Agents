"""
§5.1 — the rule pack manifest schema. This is the entire surface through
which domain behaviour enters the system. If something needs a domain word
to express, it goes in a manifest field here — never in `core/` code
(§2.2, enforced by tests/security/test_banned_vocabulary.py).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PackMeta(BaseModel):
    id: str
    name: str
    version: str
    engine_compat: str
    vendor: str | None = None
    description: str | None = None


class DimensionSpec(BaseModel):
    key: str
    label: str
    data_type: Literal["string", "number", "date", "uuid"]
    is_indexed: bool = False
    is_filterable: bool = False
    is_isolating: bool = False


class RoleSpec(BaseModel):
    code: str
    label: str
    can_approve: list[str] = Field(default_factory=list)
    cannot: list[str] = Field(default_factory=list)


class UniverseSideSpec(BaseModel):
    connector_type: str
    filter: str | None = None


class UniverseSpec(BaseModel):
    code: str
    label: str
    side_a: UniverseSideSpec
    side_b: UniverseSideSpec
    match_keys: list[str] = Field(default_factory=list)
    tolerance_profile: str
    require_dimension: list[str] = Field(default_factory=list)
    autonomy_level: Literal["A0", "A1", "A2", "A3"] = "A2"


class BreakTypeSpec(BaseModel):
    code: str
    family: str
    label: str
    risk_weight: int
    is_sensitive: bool = False
    default_route: str | None = None
    guidance_doc: str | None = None

    @field_validator("code")
    @classmethod
    def code_has_family_prefix(cls, v: str, info):
        family = info.data.get("family")
        if family and not v.startswith(f"{family}-"):
            raise ValueError(f"break type code {v!r} must start with family prefix {family!r}-")
        return v


class ToleranceRule(BaseModel):
    field: str
    type: Literal["day_window", "absolute_or_percent"]
    value: float | None = None
    absolute: float | None = None
    percent: float | None = None
    currency: str | None = None


class ToleranceProfileSpec(BaseModel):
    profile: str
    rules: list[ToleranceRule]


class RoutingCondition(BaseModel):
    family: str | None = None
    amount_gte: float | None = None


class RoutingSpec(BaseModel):
    when: RoutingCondition
    require_role: str
    allow_auto_match: bool = True
    escalate_to: str | None = None


class KnowledgeSpec(BaseModel):
    namespace: str
    document_types: list[str] = Field(default_factory=list)
    precedent_rank_below_policy: bool = True


class JournalTemplateLine(BaseModel):
    side: Literal["DR", "CR"]
    account_role: str


class JournalTemplateSpec(BaseModel):
    code: str
    label: str
    lines: list[JournalTemplateLine]
    requires_role: str | None = None


class ValidatorSpec(BaseModel):
    id: str
    hook: str
    impl: str


class EventsSpec(BaseModel):
    emit: list[str] = Field(default_factory=list)


class PackManifest(BaseModel):
    """Top-level manifest — one pack, one file, per §5.1."""

    pack: PackMeta
    dimensions: list[DimensionSpec] = Field(default_factory=list)
    roles: list[RoleSpec] = Field(default_factory=list)
    universes: list[UniverseSpec] = Field(default_factory=list)
    break_types: list[BreakTypeSpec] = Field(default_factory=list)
    tolerances: list[ToleranceProfileSpec] = Field(default_factory=list)
    routing: list[RoutingSpec] = Field(default_factory=list)
    knowledge: KnowledgeSpec | None = None
    journal_templates: list[JournalTemplateSpec] = Field(default_factory=list)
    validators: list[ValidatorSpec] = Field(default_factory=list)
    events: EventsSpec = Field(default_factory=EventsSpec)
