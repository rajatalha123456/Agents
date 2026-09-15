"""EP-04 / §5.3 — the routing *engine*. Rules themselves (which family goes
to which role) are pack data (`RoutingRule`, core/models/routing.py); this
module only resolves them against a case's facts.

§5.3's conflict rule is load-bearing: `allow_auto_match: false` always wins,
no matter how many other matching rules would otherwise allow it —
restriction beats permission, unconditionally, with no exception path.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RoutingRuleFacts:
    break_family: str
    amount_band: dict | None  # e.g. {"gte": 1000000} / {"lt": 1000}
    dimension_filter: dict | None
    required_role: str
    escalation_role: str | None
    allow_auto_match: bool


@dataclass(frozen=True)
class RoutingDecision:
    required_role: str
    escalation_role: str | None
    allow_auto_match: bool
    matched_rules: tuple[str, ...]


def _amount_matches(amount: Decimal | None, band: dict | None) -> bool:
    if band is None:
        return True
    if amount is None:
        return False
    if "gte" in band and amount < Decimal(str(band["gte"])):
        return False
    if "lt" in band and amount >= Decimal(str(band["lt"])):
        return False
    return True


def _dimensions_match(dimensions: dict, dimension_filter: dict | None) -> bool:
    if not dimension_filter:
        return True
    return all(dimensions.get(k) == v for k, v in dimension_filter.items())


def resolve_routing(
    *,
    break_family: str,
    amount: Decimal | None,
    dimensions: dict,
    rules: list[RoutingRuleFacts],
) -> RoutingDecision:
    """A case can match more than one rule (e.g. family + a high-amount
    escalation rule). All matching rules apply; `allow_auto_match` is the
    logical AND of every matched rule so a single restrictive rule can
    always veto auto-match, and `required_role`/`escalation_role` come from
    the last-matching rule with the tightest amount band (highest `gte`).
    """
    matched = [
        r for r in rules
        if r.break_family == break_family
        and _amount_matches(amount, r.amount_band)
        and _dimensions_match(dimensions, r.dimension_filter)
    ]
    if not matched:
        raise ValueError(f"no routing rule matches break_family={break_family!r}")

    def specificity(r: RoutingRuleFacts) -> Decimal:
        return Decimal(str((r.amount_band or {}).get("gte", 0)))

    tightest = max(matched, key=specificity)
    allow_auto_match = all(r.allow_auto_match for r in matched)

    return RoutingDecision(
        required_role=tightest.required_role,
        escalation_role=tightest.escalation_role,
        allow_auto_match=allow_auto_match,
        matched_rules=tuple(r.break_family for r in matched),
    )
