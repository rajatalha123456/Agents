"""§4.3 — the case lifecycle state machine, kept separate from the record
lifecycle (v2's mistake was mixing the two in one diagram).

This module is the single place that decides whether a transition is legal.
Callers (API routes, services) must go through `transition`, never set
`BreakCase.status` directly — otherwise the state machine is just a comment.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.models.break_case import BreakCaseStatus as S

# §4.3 diagram, encoded as an adjacency map. REOPENED needs its own
# permission + mandatory reason per the diagram's side note — that's
# enforced by TransitionRequest.reason below, not by a separate state.
_ALLOWED: dict[S, set[S]] = {
    S.OPEN: {S.TRIAGED},
    S.TRIAGED: {S.PROPOSED},
    S.PROPOSED: {S.UNDER_REVIEW},
    S.UNDER_REVIEW: {S.APPROVED, S.REJECTED, S.RETURNED},
    S.REJECTED: {S.TRIAGED},
    S.RETURNED: {S.TRIAGED},
    S.APPROVED: {S.ACTION_PENDING},
    S.ACTION_PENDING: {S.RESOLVED},
    S.RESOLVED: {S.CLOSED},
    S.CLOSED: {S.REOPENED},
    S.REOPENED: {S.TRIAGED},
    # CARRIED_FORWARD (§16) is reachable from any still-open state at period
    # close, and always returns to TRIAGED the following period.
    S.CARRIED_FORWARD: {S.TRIAGED},
}

_CARRY_FORWARD_ELIGIBLE = {
    S.OPEN, S.TRIAGED, S.PROPOSED, S.UNDER_REVIEW, S.REJECTED, S.RETURNED,
    S.APPROVED, S.ACTION_PENDING,
}

_REASON_REQUIRED = {S.REOPENED}


class IllegalTransition(ValueError):
    pass


@dataclass(frozen=True)
class TransitionRequest:
    case_status: S
    target: S
    reason: str | None = None
    is_period_close: bool = False


def transition(request: TransitionRequest) -> S:
    """Returns the new status, or raises IllegalTransition. Never mutates
    the ORM object itself — that's the caller's job once this says yes.
    """
    if request.is_period_close:
        if request.target != S.CARRIED_FORWARD:
            raise IllegalTransition("period close may only move a case to CARRIED_FORWARD")
        if request.case_status not in _CARRY_FORWARD_ELIGIBLE:
            raise IllegalTransition(f"{request.case_status} is not eligible for carry-forward")
        return S.CARRIED_FORWARD

    allowed = _ALLOWED.get(request.case_status, set())
    if request.target not in allowed:
        raise IllegalTransition(f"{request.case_status} -> {request.target} is not a legal transition")

    if request.target in _REASON_REQUIRED and not request.reason:
        raise IllegalTransition(f"transition to {request.target} requires a reason")

    return request.target
