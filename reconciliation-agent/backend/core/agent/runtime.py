"""
§11.2 — the agent step contract. The sequence is fixed on purpose
(predictability > flexibility in financial controls): the agent does not
plan its own steps, it runs this pipeline for every case.

This module wires the *shape* of P5 (deterministic agent, no LLM) and
P6 (LLM-backed proposals, §28 roadmap) — the actual classify/gather/
retrieve/draft steps are injected as callables so this can be unit tested
without a database or an LLM, and so P5 can ship a template-only
`draft_proposal_fn` while P6 swaps in the real one without touching this
orchestration.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.agent.budgets import CaseBudgetTracker, NotAnalysed, RunBudgetTracker
from core.agent.validators import ProposalRejected, validate_proposal
from core.config import AgentBudgets


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    status: str  # "PERSISTED" | "NOT_ANALYSED" | "ANALYSIS_FAILED"
    proposal_payload: dict | None = None
    reason: str | None = None
    llm_touched: bool = False


@dataclass
class AgentStepFunctions:
    """
    Every callable here corresponds 1:1 to a numbered step in §11.2. Each
    one may call `budget.record_tool_call()` for every read tool it uses,
    so a chatty implementation naturally exhausts its own budget instead of
    needing runtime.py to guess at tool-call counts.
    """

    load_case: Callable[[str, CaseBudgetTracker], dict]
    classify: Callable[[dict, CaseBudgetTracker], str]
    gather_candidates: Callable[[dict, str, CaseBudgetTracker], list]
    retrieve_knowledge: Callable[[str, dict, CaseBudgetTracker], list]
    retrieve_precedent: Callable[[str, dict, CaseBudgetTracker], list]
    build_context: Callable[..., Any]
    draft_proposal: Callable[[Any, CaseBudgetTracker], dict]
    validate: Callable[[dict], None] = validate_proposal  # overridable for tests
    persist: Callable[[str, dict], None] = lambda case_id, payload: None


def run_case(
    case_id: str,
    steps: AgentStepFunctions,
    budgets: AgentBudgets,
) -> CaseOutcome:
    """
    Executes §11.2 steps 1-9 for a single case. Any `NotAnalysed` raised by
    a step (budget exhaustion) or `ProposalRejected` raised by validation
    is caught here and turned into the corresponding terminal outcome —
    the case is never left in an ambiguous state, and nothing partial is
    ever returned as if it were a real proposal.
    """
    case_budget = CaseBudgetTracker(limits=budgets)
    try:
        facts = steps.load_case(case_id, case_budget)
        break_type_code = steps.classify(facts, case_budget)
        candidates = steps.gather_candidates(facts, break_type_code, case_budget)
        knowledge = steps.retrieve_knowledge(break_type_code, facts, case_budget)
        precedent = steps.retrieve_precedent(break_type_code, facts, case_budget)
        context = steps.build_context(
            facts=facts, candidates=candidates, knowledge=knowledge, precedent=precedent
        )
        proposal_payload = steps.draft_proposal(context, case_budget)
    except NotAnalysed as exc:
        return CaseOutcome(case_id=case_id, status="NOT_ANALYSED", reason=exc.reason)

    try:
        steps.validate(proposal_payload)
    except ProposalRejected as exc:
        return CaseOutcome(
            case_id=case_id, status="ANALYSIS_FAILED", reason="; ".join(exc.reasons)
        )

    steps.persist(case_id, proposal_payload)
    return CaseOutcome(
        case_id=case_id,
        status="PERSISTED",
        proposal_payload=proposal_payload,
        llm_touched=bool(case_budget.tokens_in_used or case_budget.tokens_out_used),
    )


def run_agent_run(
    case_ids: list[str],
    steps: AgentStepFunctions,
    budgets: AgentBudgets,
) -> tuple[RunBudgetTracker, list[CaseOutcome]]:
    """
    §11.4 — run-level orchestration. Stops taking new cases once the
    per-run cap or wall clock budget is hit; every case past that point is
    left `NOT_ANALYSED` and reprioritised on the next run (§11.4), never
    force-processed to "finish the queue".
    """
    run_budget = RunBudgetTracker(limits=budgets)
    outcomes: list[CaseOutcome] = []

    for case_id in case_ids:
        if not run_budget.can_start_next_case():
            run_budget.record_case_skipped(case_id, "run budget exhausted")
            outcomes.append(CaseOutcome(case_id=case_id, status="NOT_ANALYSED", reason="run budget exhausted"))
            continue

        outcome = run_case(case_id, steps, budgets)
        run_budget.record_case_done(llm_touched=outcome.llm_touched)
        if outcome.status == "NOT_ANALYSED" and outcome.reason:
            run_budget.record_case_skipped(case_id, outcome.reason)
        outcomes.append(outcome)

    return run_budget, outcomes
