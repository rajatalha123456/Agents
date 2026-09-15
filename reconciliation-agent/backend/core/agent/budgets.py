"""
§11.4 — hard per-run and per-case budgets. Every cap comes from
core.config.AgentBudgets (§32, nothing hardcoded); this module only owns
the *tracking and enforcement* mechanism: once a budget is exhausted, the
case is marked NOT_ANALYSED and the agent moves on — it never produces a
partial or guessed proposal to route around a budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.config import AgentBudgets


class NotAnalysed(Exception):
    """
    Raised internally when a case's budget is exhausted. The agent runtime
    catches this at the case level and records `agent.budget.exhausted`
    (§23) — it must never be allowed to propagate into a saved proposal.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class CaseBudgetTracker:
    """Tracks §11.4's per-case caps: tool calls and token usage."""

    limits: AgentBudgets
    tool_calls_used: int = 0
    tokens_in_used: int = 0
    tokens_out_used: int = 0
    cost_used_usd: float = 0.0

    def record_tool_call(self) -> None:
        self.tool_calls_used += 1
        if self.tool_calls_used > self.limits.tool_calls_per_case:
            raise NotAnalysed("tool_calls_per_case budget exhausted")

    def record_llm_usage(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.tokens_in_used += tokens_in
        self.tokens_out_used += tokens_out
        self.cost_used_usd += cost_usd
        if self.tokens_in_used > self.limits.llm_tokens_in_per_case:
            raise NotAnalysed("llm_tokens_in_per_case budget exhausted")
        if self.tokens_out_used > self.limits.llm_tokens_out_per_case:
            raise NotAnalysed("llm_tokens_out_per_case budget exhausted")
        if self.cost_used_usd > self.limits.llm_cost_ceiling_per_case_usd:
            raise NotAnalysed("llm_cost_ceiling_per_case budget exhausted")


@dataclass
class RunBudgetTracker:
    """
    Tracks §11.4's per-run caps: case count, wall clock, and the
    LLM-touched-breaks share alert (the most important metric in the
    section — if >12% of the queue needs the LLM, the rule engine is
    the thing that's broken, not the model).
    """

    limits: AgentBudgets
    cases_analysed: int = 0
    cases_llm_touched: int = 0
    cases_skipped: dict[str, str] = field(default_factory=dict)  # case_id -> reason
    elapsed_minutes: float = 0.0

    def can_start_next_case(self) -> bool:
        if self.cases_analysed >= self.limits.cases_per_run:
            return False
        if self.elapsed_minutes >= self.limits.wall_clock_minutes_per_run:
            return False
        return True

    def record_case_done(self, *, llm_touched: bool) -> None:
        self.cases_analysed += 1
        if llm_touched:
            self.cases_llm_touched += 1

    def record_case_skipped(self, case_id: str, reason: str) -> None:
        self.cases_skipped[case_id] = reason

    @property
    def llm_touched_share(self) -> float:
        if self.cases_analysed == 0:
            return 0.0
        return self.cases_llm_touched / self.cases_analysed

    def llm_touched_share_alert(self) -> bool:
        return self.llm_touched_share > self.limits.llm_touched_breaks_max_share
