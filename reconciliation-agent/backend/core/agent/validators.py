"""
§11.2 step 8 — validate(proposal). Output validation depends on schema and
DB lookups, never on trusting the LLM's own claims (§13.2): if a model
writes `"approved": true` into free-form output, that field simply isn't
part of the schema anywhere the platform reads from.

A proposal that fails any check here is NOT persisted (§11.2) — the
runtime raises `ProposalRejected` and records `agent.proposal.rejected_by_validator`
(§23) instead of saving a partial or guessed proposal.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.agent.tools.draft_tools import DRAFT_TABLES  # noqa: F401  (documents the write surface)


class ProposalRejected(Exception):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


@dataclass(frozen=True)
class RetrievalTraceLookup:
    """Minimal read surface the validator needs — a real DB-backed implementation lives in core/rag."""

    returned_chunk_ids: frozenset[str]
    chunk_effective_dates: dict[str, tuple[str | None, str | None]]  # chunk_id -> (from, to)


@dataclass(frozen=True)
class RecordExistenceLookup:
    """Minimal read surface for "does this ID actually exist" checks."""

    known_record_ids: frozenset[str]
    known_break_ids: frozenset[str]


def validate_proposal(
    *,
    payload: dict,
    citations: list[str],
    case_date_iso: str,
    records: RecordExistenceLookup,
    retrieval: RetrievalTraceLookup,
) -> None:
    """
    Runs every §11.2/§19.4/§13.2 check. Raises ProposalRejected with every
    failure found (not just the first) so a rejected proposal's audit event
    is actually useful for debugging the rule/prompt that produced it.
    """
    reasons: list[str] = []

    # "Hallucinated ID" (§29.2) — every record/break id the proposal
    # references must actually exist.
    for ref_field in ("record_ids", "break_ids"):
        for rid in payload.get(ref_field, []):
            known_ids = records.known_record_ids if ref_field == "record_ids" else records.known_break_ids
            if rid not in known_ids:
                reasons.append(f"{ref_field} contains unknown id {rid!r}")

    # Citation resolution (§19.4) — must have been actually returned by
    # retrieval, and its effective-date window must cover the case date.
    for chunk_id in citations:
        if chunk_id not in retrieval.returned_chunk_ids:
            reasons.append(f"citation {chunk_id!r} was not present in the retrieval trace")
            continue
        eff_from, eff_to = retrieval.chunk_effective_dates.get(chunk_id, (None, None))
        if eff_from and case_date_iso < eff_from:
            reasons.append(f"citation {chunk_id!r} not yet effective on {case_date_iso}")
        if eff_to and case_date_iso > eff_to:
            reasons.append(f"citation {chunk_id!r} no longer effective on {case_date_iso}")

    # Schema-not-trust (§13.2) — fields the model has no business setting.
    for forbidden_field in ("approved", "posted", "certified", "write_off_executed"):
        if forbidden_field in payload:
            reasons.append(
                f"payload sets {forbidden_field!r}, which is not a field the agent may set"
            )

    if reasons:
        raise ProposalRejected(reasons)
