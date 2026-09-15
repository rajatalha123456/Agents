"""§8.3 L3 — group matching: 1:N, N:1, N:M subset-sum with pruning.

Subset-sum is NP-hard, so this is bounded by config guardrails
(`GroupMatchGuardrails`, §11.4/§8.3), not by algorithmic cleverness:
max group size, max candidate set per attempt, and a wall-clock budget per
group. Exceeding the candidate set cap doesn't silently truncate — it
raises so the caller can record a DAT-07 "candidate explosion" break instead
of guessing which subset of 500 candidates to consider.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from core.config import GroupMatchGuardrails
from core.matching.exact import MatchRecord


class CandidateExplosion(Exception):
    """Raised when a block exceeds `max_candidate_pool_per_group` (DAT-07)."""


@dataclass(frozen=True)
class GroupMatch:
    side_a_ids: tuple[str, ...]
    side_b_ids: tuple[str, ...]
    net_amount: Decimal


def _signed(records: list[MatchRecord]) -> dict[str, Decimal]:
    return {r.id: (r.amount if r.direction == "CR" else -r.amount) for r in records}


def find_group_matches(
    side_a: list[MatchRecord],
    side_b: list[MatchRecord],
    tolerance: Decimal,
    guardrails: GroupMatchGuardrails,
) -> list[GroupMatch]:
    """One side supplies the anchor set to sum against; group confidence is
    always lower than L1/L2 (§8.3 — "accidental sum matching is real") so the
    caller, not this function, applies that confidence discount. This
    function only finds candidate sums that net to (approximately) zero.
    """
    candidates = side_a + side_b
    if len(candidates) > guardrails.max_candidate_pool_per_group:
        raise CandidateExplosion(
            f"{len(candidates)} candidates exceeds cap of {guardrails.max_candidate_pool_per_group}"
        )

    signed = _signed(candidates)
    deadline = time.monotonic() + guardrails.time_budget_ms_per_group / 1000
    results: list[GroupMatch] = []
    seen_a: set[str] = set()
    seen_b: set[str] = set()

    max_size = min(guardrails.max_group_size, len(candidates))
    for size in range(2, max_size + 1):
        for combo in combinations(candidates, size):
            if time.monotonic() > deadline:
                return results
            ids = {r.id for r in combo}
            a_ids = tuple(r.id for r in combo if r.side == "SOURCE_A")
            b_ids = tuple(r.id for r in combo if r.side == "SOURCE_B")
            if not a_ids or not b_ids:
                continue
            if ids & seen_a or ids & seen_b:
                continue
            net = sum((signed[r.id] for r in combo), Decimal("0"))
            if abs(net) <= tolerance:
                results.append(GroupMatch(a_ids, b_ids, net))
                seen_a.update(a_ids)
                seen_b.update(b_ids)
    return results
