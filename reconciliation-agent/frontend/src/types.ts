export type RecordRow = { id: string; side: string; account: string; period: string; amount: string; currency: string; direction: string; value_date: string; reference: string; description: string; status: string; source_file: string; raw_payload: Record<string, string> };
export type BreakCase = { id: string; title: string; code: string; period: string; account: string; currency: string; amount: string; reference: string; description: string; record_ids: string[]; status: string; risk: string; created_at: string; value_date: string; owner: string; proposal: null | { id: string; maker: string; text: string; evidence_ids: string[]; method: string; version: string; created_at: string }; decision: null | { actor: string; reason: string; action: string; created_at: string }; external_ref: string | null };
export type Batch = { id: string; filename: string; side: string; account: string; period: string; row_count: number; valid_count: number; status: string; errors: { line: number; reason: string }[]; created_at: string; checksum: string; control_totals: Record<string, { row_count: number; debit_sum: string; credit_sum: string }>; source_format: string; statement_check: null | { opening_balance: string; opening_direction: string; closing_balance: string; closing_direction: string; movement: string; unexplained: string } };
export type Run = { id: string; kind: string; period: string; created_at: string; status: string; matched?: number; cases: number; skipped?: number; budget?: number; model?: string; llm_touched?: number; llm_input_tokens?: number; llm_output_tokens?: number; llm_touched_share?: number; llm_share_breach?: boolean; rule_version: string };
export type AuditEvent = { actor: string; event_type: string; created_at: string; after: Record<string, unknown>; hash_self: string; hash_prev: string | null };
export type JournalDraft = { id: string; case_id: string; period: string; lines: { side: string; account_role: string; amount: string }[]; reason: string; maker: string; status: string; created_at: string; decision: null | { actor: string; reason: string; action: string; created_at: string } };
export type Workspace = { records: RecordRow[]; breaks: BreakCase[]; imports: Batch[]; matches: {id: string; record_ids: string[]; period: string; rule: string; rule_version: string; created_at: string; net_amount?: string; reason?: string; reversed?: boolean; reversal?: {actor:string; reason:string; created_at:string}}[]; journal_drafts: JournalDraft[]; runs: Run[]; audit: AuditEvent[]; periods: Record<string, { status: string; actor: string; created_at: string; reason: string }>; sample_loaded: boolean; audit_valid: boolean; mode: string };

// Mirrors core/packs/manifest_schema.py::PackManifest — the real installed
// pack manifest returned by GET /api/packs, not a UI-invented shape.
export type Pack = {
  pack: { id: string; name: string; version: string; engine_compat: string; vendor: string | null; description: string | null };
  dimensions: { key: string; label: string; data_type: string; is_indexed: boolean; is_filterable: boolean; is_isolating: boolean }[];
  roles: { code: string; label: string; can_approve: string[]; cannot: string[] }[];
  break_types: { code: string; family: string; label: string; risk_weight: number; is_sensitive: boolean; default_route: string | null; guidance_doc: string | null }[];
  tolerances: { profile: string; rules: { field: string; type: string; value: number | null; absolute: number | null; percent: number | null; currency: string | null }[] }[];
  routing: { when: { family: string | null; amount_gte: number | null }; require_role: string; allow_auto_match: boolean; escalate_to: string | null }[];
};

// Mirrors workbench/mock_data.py::model_governance_snapshot — a clearly
// labeled synthetic calibration dataset (`synthetic: true`), not real
// historical match dispositions.
export type ModelGovernance = {
  synthetic: boolean;
  note: string;
  sample_size: { train: number; test: number };
  raw_ece: number;
  calibrated_ece: number;
  ece_target: number;
  reliability_diagram: { bin_lower: number; bin_upper: number; mean_predicted: number; observed_frequency: number; count: number }[];
  circuit_breaker: { tripped: boolean; breach: null | { metric: string; observed: number; target: number } };
  false_match_budget: { auto_match_false_rate_max: number; suggest_acceptance_rate_min: number; suggest_false_accept_max: number; calibration_ece_max: number };
  observed_metrics: { auto_match_false_rate: number; suggest_acceptance_rate: number; suggest_false_accept_rate: number };
};

// Mirrors workbench/mock_data.py::pilot_tenant_snapshot — `is_dummy: true`
// always; `activity_to_date` is real data from this local workspace.
// Mirrors workbench/service.py::admin_config_snapshot — real values read
// straight from core.config.get_settings(), never a UI-invented shape.
export type AdminConfig = {
  queue_priority_weights: Record<string, number>;
  confidence_band_thresholds: Record<string, number>;
  false_match_budget: Record<string, number>;
  agent_budgets: Record<string, number>;
  group_match_guardrails: Record<string, number>;
  ageing_and_roll_forward: { aged_break_high_risk_days: number; carried_forward_escalation_count: number };
  suppress_rule_max_expiry_days: number;
  scheduler: { interval_seconds: number; actor: string };
  llm: { provider: string; model: string; configured: boolean };
};

export type PilotSnapshot = {
  is_dummy: boolean;
  note: string;
  tenant: { id: string; name: string; status: string; base_currency: string; timezone: string };
  activity_to_date: { imports: number; breaks_created: number; breaks_resolved: number; agent_runs: number; reconciliation_runs: number };
};
