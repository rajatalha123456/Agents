"""Challenge and override: explains selection decisions from stored facts,
and records auditor overrides with a reason in the audit trail.

Every answer is assembled from stored facts. Nothing is generated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from .audit_trail import AuditTrail

_NON_SELECTION_NOTE = (
    "Non-selection is not a conclusion that the item is free of "
    "misstatement. The statistical conclusion covers the population as a "
    "whole, not this item individually."
)

_JUDGMENTAL_WARNING = (
    "This item was selected judgmentally. Any misstatement found is a "
    "known misstatement and is not extrapolated to the population."
)

_BASIS_REASONS = {
    "mus_certainty_item": "Certainty item: book value equals or exceeds the sampling interval, so it was selected with certainty.",
    "mus_systematic": "A monetary unit within this item fell at a systematically drawn sampling point (selection probability = amount / interval).",
    "high_risk_mandatory": "Risk score met or exceeded the high-risk threshold; included as a mandatory judgmental item.",
    "random_control": "Drawn in the random control stratum, independent of risk score by design.",
    "negative_balance_100pct": "Credit / negative balance; tested 100% rather than via monetary unit sampling.",
    "zero_balance_review": "Zero balance; reviewed separately since MUS cannot select zero-value items.",
    "auditor_manual_inclusion": "Manually added to the sample by the auditor.",
}


class ChallengeAction(str, Enum):
    ACCEPT = "accept"
    ADD_TO_SAMPLE = "add_to_sample"
    REMOVE_FROM_SAMPLE = "remove_from_sample"
    OVERRIDE_SEVERITY = "override_severity"
    REQUEST_RERUN = "request_rerun"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Evidence:
    item_id: str
    selected: bool
    selection_basis: str | None
    reason: str
    facts: dict
    rules_fired: list[dict] = field(default_factory=list)
    anomaly_attribution: list[dict] = field(default_factory=list)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "selected": self.selected,
            "selection_basis": self.selection_basis,
            "reason": self.reason,
            "facts": self.facts,
            "rules_fired": self.rules_fired,
            "anomaly_attribution": self.anomaly_attribution,
            "warnings": list(self.warnings),
        }


def build_evidence(
    item_id: str,
    population: pd.DataFrame,
    sample_result,
    rule_result=None,
    anomaly_result=None,
    risk_result=None,
    item_id_col: str = "item_id",
    amount_col: str = "amount",
    sampling_interval: float | None = None,
    high_risk_threshold: float | None = None,
) -> Evidence:
    pop_row = population[population[item_id_col] == item_id]
    if pop_row.empty:
        raise ValueError(f"item '{item_id}' not found in population")
    row = pop_row.iloc[0]
    row_idx = pop_row.index[0]

    sample_items = sample_result.items
    sample_row = None
    if len(sample_items):
        match = sample_items[sample_items[item_id_col] == item_id]
        if not match.empty:
            sample_row = match.iloc[0]

    warnings: list[str] = []
    rules_fired: list[dict] = []
    anomaly_attribution: list[dict] = []

    if rule_result is not None and row_idx < len(rule_result.fired_rules_by_row):
        rules_fired = rule_result.fired_rules_by_row[row_idx]
    if anomaly_result is not None and row_idx < len(anomaly_result.attribution):
        anomaly_attribution = anomaly_result.attribution[row_idx]

    amount = float(row[amount_col])
    facts = {"item_id": item_id, "amount": amount}

    if sample_row is not None:
        basis = str(sample_row["_selection_basis"])
        reason = _BASIS_REASONS.get(basis, "Selected.")
        if basis == "mus_systematic" and sampling_interval:
            facts["selection_probability"] = round(min(amount / sampling_interval, 1.0), 6)
        if not _basis_projectable(basis):
            warnings.append(_JUDGMENTAL_WARNING)
        return Evidence(
            item_id=item_id, selected=True, selection_basis=basis, reason=reason,
            facts=facts, rules_fired=rules_fired,
            anomaly_attribution=anomaly_attribution, warnings=tuple(warnings),
        )

    # Not selected.
    facts["gap_to_high_risk_threshold"] = (
        None if high_risk_threshold is None or risk_result is None
        else round(high_risk_threshold - float(risk_result.scores[row_idx]), 4)
    )
    if sampling_interval:
        facts["selection_probability"] = round(min(amount / sampling_interval, 1.0), 6)
        facts["book_value_for_certain_selection"] = sampling_interval

    reason = _NON_SELECTION_NOTE
    warnings.append(_NON_SELECTION_NOTE)

    return Evidence(
        item_id=item_id, selected=False, selection_basis=None, reason=reason,
        facts=facts, rules_fired=rules_fired,
        anomaly_attribution=anomaly_attribution, warnings=tuple(warnings),
    )


def _basis_projectable(basis: str) -> bool:
    return basis in ("mus_systematic", "mus_certainty_item", "random_control")


def compare_items(item_a: str, item_b: str, population: pd.DataFrame, sample_result, **kwargs) -> dict:
    evidence_a = build_evidence(item_a, population, sample_result, **kwargs)
    evidence_b = build_evidence(item_b, population, sample_result, **kwargs)

    rules_a = {r["rule_id"] for r in evidence_a.rules_fired}
    rules_b = {r["rule_id"] for r in evidence_b.rules_fired}

    return {
        "item_a": evidence_a.as_dict(),
        "item_b": evidence_b.as_dict(),
        "rules_only_in_a": sorted(rules_a - rules_b),
        "rules_only_in_b": sorted(rules_b - rules_a),
        "rules_in_both": sorted(rules_a & rules_b),
        "amount_difference": round(evidence_a.facts["amount"] - evidence_b.facts["amount"], 2),
    }


MIN_OVERRIDE_REASON_LENGTH = 10
OVERRIDE_AUDIT_ACTION = "challenge.override"
OVERRIDE_NOTE = (
    "This override is recorded against the original sample. The "
    "statistical conclusion for the run is unchanged. A materially "
    "different sample composition requires a re-run under a new "
    "policy version rather than an edit."
)


def build_override_payload(item_id: str, action: ChallengeAction, reason: str,
                            before: dict, after: dict, sampling_run_id: str) -> dict:
    """The payload shape apply_override() writes to the trail, exposed so
    callers using an async trail implementation (PgAuditTrail) that
    apply_override's synchronous call signature can't drive directly can
    still write the identical event without duplicating this shape.
    """
    if len(reason.strip()) < MIN_OVERRIDE_REASON_LENGTH:
        raise ValueError(f"override reason must be at least {MIN_OVERRIDE_REASON_LENGTH} characters")
    return {
        "item_id": item_id,
        "action": action.value if isinstance(action, ChallengeAction) else action,
        "reason": reason,
        "before_state": before,
        "after_state": after,
        "sampling_run_id": sampling_run_id,
    }


def apply_override(
    trail: AuditTrail,
    actor: str,
    item_id: str,
    action: ChallengeAction,
    reason: str,
    before: dict,
    after: dict,
    sampling_run_id: str,
) -> dict:
    payload = build_override_payload(item_id, action, reason, before, after, sampling_run_id)
    event = trail.append(actor=actor, action=OVERRIDE_AUDIT_ACTION, subject=item_id, payload=payload)

    return {
        "event_hash": event.event_hash,
        "sequence": event.sequence,
        "note": OVERRIDE_NOTE,
    }
