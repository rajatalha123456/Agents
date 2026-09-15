// Hand-written types mirroring the backend's Pydantic response models
// (sampling/api_v1/*.py). A real deployment would generate these from
// the live OpenAPI schema (e.g. openapi-typescript) so they can never
// drift from the server; that codegen step needs the backend running
// and reachable at build time, which isn't wired into this pass -- these
// are written to match the schema as of Phase 4 and should be replaced
// by generated types as the next step, not maintained by hand long-term.

export type Role = "viewer" | "auditor" | "reviewer" | "admin";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
}

export interface CurrentUser {
  user_id: string;
  tenant_id: string;
  role: Role;
  permissions: string[];
}

export interface TenantSettings {
  id: string;
  name: string;
  slug: string;
  data_residency_region: string;
  llm_enabled: boolean;
  llm_provider: string | null;
  llm_model: string | null;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
}

export interface EngagementOut {
  id: string;
  name: string;
  client_name: string;
  period_start: string | null;
  period_end: string | null;
  status: string;
  performance_materiality: string | null;
}

export interface DatasetOut {
  id: string;
  filename: string;
  ingestion_status: "pending" | "running" | "complete" | "failed";
  row_count: number | null;
  column_count: number | null;
  dataset_fingerprint: string | null;
  ingestion_warnings: string[] | null;
  ingestion_error: string | null;
}

export interface ColumnProfile {
  dtype: string;
  null_count: number;
  null_pct: number;
  distinct_count?: number;
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  p95?: number;
  negative_count?: number;
  zero_count?: number;
  sample_values?: string[];
  note?: string;
}

export interface PolicyOut {
  id: string;
  engagement_id: string;
  policy_version: string;
  tolerable_misstatement: string | null;
  confidence_level: number | null;
  approved_by: string | null;
}

export interface SampleSizeWorkpaper {
  sample_size: number;
  sampling_interval: number;
  book_value: number;
  tolerable_misstatement: number;
  expected_misstatement: number;
  confidence_level: number;
  reliability_factor: number;
  expansion_factor: number;
  adjusted_tolerable: number;
  basis: string;
}

export interface RulePackOut {
  id: string;
  pack_id: string;
  pack_version: string;
  owner: string | null;
  approved_by: string | null;
}

export interface RiskRunOut {
  id: string;
  run_id: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled";
  progress_pct: number;
  dataset_fingerprint: string | null;
  error_message: string | null;
  warnings: string[] | null;
  risk_manifest: { formula_version?: string } | null;
  anomaly_manifest: Record<string, unknown> | null;
  rules_manifest: Record<string, unknown> | null;
  sample_manifest: Record<string, unknown> | null;
}

export type SelectionBasis =
  | "mus_systematic"
  | "mus_certainty_item"
  | "random_control"
  | "high_risk_mandatory"
  | "negative_balance_100pct"
  | "zero_balance_review"
  | "auditor_manual_inclusion";

export const PROJECTABLE_BASES: SelectionBasis[] = ["mus_systematic", "mus_certainty_item", "random_control"];

export interface SampleItemOut {
  item_id: string;
  stratum: string;
  selection_basis: SelectionBasis;
  projectable: boolean;
  amount: string | null;
  audit_value: string | null;
}

export interface TransactionRow {
  item_id: string;
  amount: string | null;
  risk_score: number | null;
  selected: boolean;
  stratum: string | null;
  selection_basis: SelectionBasis | null;
}

export interface EvaluationWorkpaper {
  known_misstatement: number;
  projected_misstatement: number;
  most_likely_misstatement: number;
  basic_precision: number;
  incremental_allowance: number;
  allowance_for_sampling_risk: number;
  upper_misstatement_limit: number;
  tolerable_misstatement: number;
  projected_understatement: number;
  judgmental_known_misstatement: number;
  conclusion: "ACCEPT" | "REJECT" | "INCONCLUSIVE";
  conclusion_basis: string;
  projectable_count: number;
  certainty_count: number;
  judgmental_count: number;
  warnings: string[];
}

export interface EvidenceOut {
  item_id: string;
  selected: boolean;
  selection_basis: SelectionBasis | null;
  reason: string;
  facts: Record<string, unknown>;
  rules_fired: Array<{ rule_id: string; severity: string; description: string; explanation: string; owner: string }>;
  anomaly_attribution: Array<{ feature: string; robust_z: number; value: number }>;
  warnings: string[];
}

export interface NarrateResult {
  evidence: EvidenceOut;
  narrative: string | null;
  fallback_message?: string;
  grounding: { grounded: boolean; ungrounded_numbers: string[] };
}

export interface BenchmarkReport {
  k: number;
  n: number;
  findings_total: number;
  base_rate: number;
  precision: number;
  recall: number;
  lift: number;
  lift_ci_low: number;
  lift_ci_high: number;
  statement: string;
  warnings: string[];
}

export type BenchmarkVerdict = "BEATS_RANDOM" | "WORSE_THAN_RANDOM" | "NOT_DISTINGUISHABLE_FROM_RANDOM" | "INSUFFICIENT_DATA";

export interface AuditEventOut {
  sequence: number;
  timestamp: string;
  actor: string;
  action: string;
  subject: string;
  payload: Record<string, unknown>;
}
