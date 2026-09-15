"""
Central configuration surface for the core engine.

Spec §32: "kuch bhi hardcode nahi" — tolerance profiles, confidence bands,
queue priority weights, agent budgets, autonomy levels, approval limits,
ageing windows, retention, etc. all come from configuration, not code.

This module defines the *shape* of that configuration (typed, validated)
and loads it from environment variables / a config file. Domain packs
supply their own values through the pack manifest (see core/packs); this
module only owns the engine-level defaults and the tenant/runtime wiring.

Nothing in this file may name a concept that belongs to a specific rule
pack rather than the core engine — see the banned-word list enforced by
tests/security/test_banned_vocabulary.py.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, if one exists — never committed (see .gitignore); this is
# purely a local-dev convenience so `GEMINI_API_KEY` doesn't have to be
# exported by hand in every shell. Production deployments set real
# environment variables / a secrets vault instead (§6.3's rule on
# credentials applies to this key too).
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class QueuePriorityWeights(BaseSettings):
    """§1.4 — priority formula weights. Configured, never hardcoded per-tenant."""

    w1_amount: float = 1.0
    w2_risk_weight: float = 2.0
    w3_age_days: float = 0.5
    w4_close_deadline_pressure: float = 3.0
    w5_repeat_counterparty: float = 1.0


class ConfidenceBandThresholds(BaseSettings):
    """§9.2 — calibrated-probability cut points between bands."""

    auto_min_p: float = 0.98
    suggest_min_p: float = 0.85
    investigate_min_p: float = 0.60


class FalseMatchBudget(BaseSettings):
    """§9.3 — targets that trip the auto-match circuit breaker on breach."""

    auto_match_false_rate_max: float = 1.0 / 10_000
    suggest_acceptance_rate_min: float = 0.80
    suggest_false_accept_max: float = 0.005
    calibration_ece_max: float = 0.05


class AgentBudgets(BaseSettings):
    """§11.4 — hard caps per agent run. Breach => NOT_ANALYSED, never a guess."""

    cases_per_run: int = 500
    tool_calls_per_case: int = 12
    llm_tokens_in_per_case: int = 8_000
    llm_tokens_out_per_case: int = 1_500
    llm_cost_ceiling_per_case_usd: float = 0.50
    wall_clock_minutes_per_run: int = 90
    llm_touched_breaks_max_share: float = 0.12


class GroupMatchGuardrails(BaseSettings):
    """§8.3 — subset-sum group matching is NP-hard; these caps keep it bounded."""

    max_group_size: int = 8
    max_candidate_pool_per_group: int = 200
    time_budget_ms_per_group: int = 500


class RetrievalConfig(BaseSettings):
    """§19.3 — RAG retrieval knobs."""

    top_k_chunks: int = 6
    use_cross_encoder_rerank: bool = False


class LLMConfig(BaseSettings):
    """
    §27 — "Provider-neutral LLM adapter (Anthropic default) — Model swap
    without logic change." `provider`/`model` are swappable; `api_key`
    unset is a first-class state, not an error — §13.5's deterministic
    fallback engages whenever it (or any call) is unavailable, so the core
    reconciliation flow is never blocked on an LLM being configured.
    """

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT_ENV_FILE) if _REPO_ROOT_ENV_FILE.exists() else None,
        extra="ignore", populate_by_name=True,
    )

    provider: str = "gemini"
    model: str = "gemini-3.6-flash"
    api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    request_timeout_seconds: float = 20.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECON_", env_nested_delimiter="__")

    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://recon:recon@localhost:5432/reconciliation",
        description="Application DB connection. Must use a tenant-scoped role, "
        "never a superuser (§20).",
    )
    agent_db_role: str = "agent_runtime"

    default_agent_cron_hour_local: int = 2  # §11.1 schedule.cron default 02:00 tenant tz

    queue_weights: QueuePriorityWeights = Field(default_factory=QueuePriorityWeights)
    confidence_bands: ConfidenceBandThresholds = Field(default_factory=ConfidenceBandThresholds)
    false_match_budget: FalseMatchBudget = Field(default_factory=FalseMatchBudget)
    agent_budgets: AgentBudgets = Field(default_factory=AgentBudgets)
    group_match: GroupMatchGuardrails = Field(default_factory=GroupMatchGuardrails)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    suppress_rule_max_expiry_days: int = 90  # §11.3
    carried_forward_escalation_count: int = 3  # §16
    aged_break_high_risk_days: int = 90  # §16


@lru_cache
def get_settings() -> Settings:
    return Settings()
