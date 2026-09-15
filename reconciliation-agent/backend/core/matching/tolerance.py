"""§8.1 L2 — tolerance-based matching against an approved tolerance profile.

Still deterministic: a pair either satisfies every rule in the profile or it
doesn't. The profile itself (§4.2 `ToleranceProfile.rules`) is pack/tenant
data, never hardcoded here — this module only applies it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from core.matching.exact import MatchRecord


@dataclass(frozen=True)
class ToleranceRule:
    field: str
    type: str  # "day_window" | "absolute_or_percent"
    value: int | None = None          # day_window
    absolute: Decimal | None = None   # absolute_or_percent
    percent: float | None = None      # absolute_or_percent
    currency: str | None = None       # absolute_or_percent, optional scoping

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ToleranceRule":
        return cls(
            field=raw["field"],
            type=raw["type"],
            value=raw.get("value"),
            absolute=Decimal(str(raw["absolute"])) if "absolute" in raw else None,
            percent=raw.get("percent"),
            currency=raw.get("currency"),
        )


def _within_day_window(a: date, b: date, window: int) -> bool:
    return abs((a - b).days) <= window


def _within_amount_band(a: Decimal, b: Decimal, rule: ToleranceRule) -> bool:
    delta = abs(a - b)
    if rule.currency is not None:
        # Scoped rule only applies within its currency; a mismatched currency
        # pair is out of this rule's jurisdiction, not automatically a pass.
        return True
    bounds = []
    if rule.absolute is not None:
        bounds.append(rule.absolute)
    if rule.percent is not None:
        bounds.append(max(a, b) * Decimal(str(rule.percent)))
    if not bounds:
        return delta == 0
    return delta <= max(bounds)


def satisfies_rule(a: MatchRecord, b: MatchRecord, rule: ToleranceRule) -> bool:
    if rule.field == "value_date" and rule.type == "day_window":
        return _within_day_window(a.value_date, b.value_date, rule.value or 0)
    if rule.field == "amount" and rule.type == "absolute_or_percent":
        if rule.currency is not None and rule.currency != a.currency:
            return True  # rule doesn't govern this currency; deferred to another rule
        return _within_amount_band(a.amount, b.amount, rule)
    raise ValueError(f"unsupported tolerance rule: {rule.field}/{rule.type}")


def tolerance_pairs(
    records: list[MatchRecord], rules: list[ToleranceRule]
) -> list[tuple[str, str, list[str]]]:
    """Candidates blocked by (account, currency, direction, isolation), then
    checked against every rule. Only unambiguous 1:1 pairs are returned —
    same discipline as L1 exact (§8.1: L2 is deterministic too).

    Returns (side_a_id, side_b_id, matched_rule_fields) so the caller can
    record which rule fired (§8.2's `get_match_rule_result`).
    """
    blocks: dict[tuple, dict[str, list[MatchRecord]]] = defaultdict(lambda: {"SOURCE_A": [], "SOURCE_B": []})
    for row in records:
        if row.side not in ("SOURCE_A", "SOURCE_B"):
            raise ValueError("invalid source side")
        if not row.reference:
            continue
        key = (row.account, row.currency, row.direction, row.isolation)
        blocks[key][row.side].append(row)

    results: list[tuple[str, str, list[str]]] = []
    for sides in blocks.values():
        candidates = []
        for a in sides["SOURCE_A"]:
            matches = [b for b in sides["SOURCE_B"] if all(satisfies_rule(a, b, r) for r in rules)]
            if len(matches) == 1:
                candidates.append((a, matches[0]))
        # enforce global 1:1 uniqueness within the block, both directions
        b_counts: dict[str, int] = defaultdict(int)
        for _, b in candidates:
            b_counts[b.id] += 1
        for a, b in candidates:
            if b_counts[b.id] == 1:
                results.append((a.id, b.id, [r.field for r in rules]))
    return results
