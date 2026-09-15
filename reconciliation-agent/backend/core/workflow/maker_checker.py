"""§18.2 — maker-checker enforcement.

Three rules, all load-bearing:
1. The actor who created/submitted a proposal or draft can never approve it
   — even if they hold a checker role elsewhere.
2. Accepting an agent's proposal counts the accepting human as *maker*, not
   checker (§18.2) — so an agent-authored proposal above the approval limit
   still needs two distinct humans, not one.
3. Reopening a closed case needs a distinct permission plus a mandatory
   reason (also enforced by `core.breaks.lifecycle`, but checked again here
   at the workflow layer since reopen is a workflow action, not a lifecycle
   detail the caller should have to know about).
"""
from __future__ import annotations

from dataclasses import dataclass


class MakerCheckerViolation(ValueError):
    pass


@dataclass(frozen=True)
class ApprovalRequest:
    made_by: str  # human actor id, or "AGENT"
    checked_by: str
    checker_has_required_role: bool
    reopen_permission_granted: bool = True
    reopen_reason: str | None = None
    is_reopen: bool = False


def authorize_approval(request: ApprovalRequest) -> None:
    """Raises MakerCheckerViolation on any breach; returns None on success.

    An `AGENT`-made proposal has no "same actor" conflict by definition —
    a human always accepts it, and that human is the maker (§18.2), so a
    *second*, distinct human is still required to check it. That second
    check happens at a layer above this one (whoever accepted becomes the
    new `made_by` on the resulting draft); this function only ever sees the
    final maker/checker pair.
    """
    if request.made_by == request.checked_by:
        raise MakerCheckerViolation("maker cannot approve their own submission")

    if not request.checker_has_required_role:
        raise MakerCheckerViolation("checker does not hold the required role for this approval")

    if request.is_reopen:
        if not request.reopen_permission_granted:
            raise MakerCheckerViolation("actor lacks the reopen permission")
        if not request.reopen_reason:
            raise MakerCheckerViolation("reopen requires a mandatory reason")
