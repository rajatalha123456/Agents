"""LLM orchestration for schema understanding and grounded narration.

The LLM interprets schemas, proposes preprocessing plans, and narrates
retrieved evidence. It never computes risk, never selects items, and sees
only the schema profile (aggregate statistics), never raw population data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

ALLOWED_PREPROCESSING_STEPS = {
    "parse_type": {"column", "target_type"},
    "parse_datetime": {"column", "format"},
    "strip_whitespace": {"column"},
    "normalize_currency": {"column", "target_currency"},
    "map_schema": {"source_column", "target_field"},
    "encode_categorical": {"column", "method"},
    "scale_numeric": {"column", "method"},
    "engineer_feature": {"name", "source_columns", "formula"},
    "flag_condition": {"name", "column", "condition"},
}

FORBIDDEN_STEPS = {
    "drop_outliers",
    "drop_duplicates",
    "drop_missing",
    "drop_rare_categories",
    "filter_rows",
    "execute_sql",
    "execute_python",
    "delete",
    "update",
}


class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str: ...


@dataclass(frozen=True)
class SchemaUnderstanding:
    column_roles: dict
    preprocessing_plan: list[dict]
    leakage_candidates: list[str]
    raw_response: str


@dataclass(frozen=True)
class PlanValidation:
    valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)
    validated_plan: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GroundingReport:
    grounded: bool
    ungrounded_numbers: tuple[str, ...] = field(default_factory=tuple)


def validate_preprocessing_plan(plan: list[dict], available_columns: set[str]) -> PlanValidation:
    errors: list[str] = []
    validated: list[dict] = []

    for i, step in enumerate(plan):
        step_type = step.get("step")
        if step_type in FORBIDDEN_STEPS:
            errors.append(f"step {i}: '{step_type}' is forbidden -- data may never be removed")
            continue
        if step_type not in ALLOWED_PREPROCESSING_STEPS:
            errors.append(f"step {i}: unknown step type '{step_type}'")
            continue

        allowed_params = ALLOWED_PREPROCESSING_STEPS[step_type]
        params = step.get("params", {})
        unknown_params = set(params.keys()) - allowed_params
        if unknown_params:
            errors.append(f"step {i} ('{step_type}'): unknown parameter(s) {sorted(unknown_params)}")
            continue

        referenced_columns = [
            v for k, v in params.items()
            if k in ("column", "source_column") and isinstance(v, str)
        ]
        referenced_columns += [
            c for c in params.get("source_columns", []) if isinstance(c, str)
        ]
        missing_columns = [c for c in referenced_columns if c not in available_columns]
        if missing_columns:
            errors.append(f"step {i} ('{step_type}'): unknown column(s) {missing_columns}")
            continue

        validated.append(step)

    return PlanValidation(valid=not errors, errors=tuple(errors), validated_plan=validated)


_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*%?")


def _collect_evidence_numbers(evidence: dict, tolerance: float) -> set[float]:
    numbers: set[float] = set()

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)
        elif isinstance(obj, (int, float)):
            numbers.add(round(float(obj), 2))

    walk(evidence)
    return numbers


def check_grounding(narrative: str, evidence: dict, tolerance: float = 0.01) -> GroundingReport:
    evidence_numbers = _collect_evidence_numbers(evidence, tolerance)
    ungrounded = []

    for match in _NUMBER_RE.finditer(narrative):
        text = match.group().rstrip("%")
        cleaned = text.replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        # Ignore small integers used in ordinary prose (e.g. "two rules fired").
        if value == int(value) and abs(value) <= 20:
            continue
        found = any(abs(value - ev) <= max(tolerance, abs(ev) * tolerance) for ev in evidence_numbers)
        if not found:
            ungrounded.append(match.group())

    return GroundingReport(grounded=not ungrounded, ungrounded_numbers=tuple(ungrounded))


_FALLBACK_MESSAGE = (
    "The generated narrative could not be verified against the retrieved "
    "evidence and has been withheld. The structured evidence above is "
    "complete and may be reviewed directly."
)


class LLMOrchestrator:
    def __init__(self, client: LLMClient, model_identifier: str, prompt_version: str, redactor=None):
        self.client = client
        self.model_identifier = model_identifier
        self.prompt_version = prompt_version
        self.redactor = redactor

    def understand_schema(self, schema_profile: dict, business_context: str = "") -> SchemaUnderstanding:
        system = (
            "You are an audit data schema analyst. You are given aggregate "
            "column statistics only, never raw records. Propose column "
            "roles (item_id, amount, timestamp, entity) and a preprocessing "
            "plan using only allowed steps. Flag any column that could leak "
            "the outcome being predicted."
        )
        user = f"Schema profile: {schema_profile}\nBusiness context: {business_context}"
        raw = self.client.complete(system=system, user=user)

        return SchemaUnderstanding(
            column_roles={}, preprocessing_plan=[], leakage_candidates=[], raw_response=raw,
        )

    def narrate_challenge(self, question: str, evidence: dict) -> dict:
        system = (
            "You are an audit assistant narrating evidence that has already "
            "been computed. Do not introduce any fact, number, or "
            "conclusion that is not present in the evidence provided."
        )
        user = f"Question: {question}\nEvidence: {evidence}"
        narrative = self.client.complete(system=system, user=user)

        grounding = check_grounding(narrative, evidence)
        if grounding.grounded:
            return {
                "evidence": evidence,
                "narrative": narrative,
                "grounding": {"grounded": True, "ungrounded_numbers": []},
            }
        return {
            "evidence": evidence,
            "narrative": None,
            "fallback_message": _FALLBACK_MESSAGE,
            "grounding": {
                "grounded": False,
                "ungrounded_numbers": list(grounding.ungrounded_numbers),
            },
        }
