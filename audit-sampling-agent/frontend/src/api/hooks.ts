import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import type {
  AuditEventOut,
  BenchmarkReport,
  BenchmarkVerdict,
  CurrentUser,
  DatasetOut,
  EngagementOut,
  EvaluationWorkpaper,
  EvidenceOut,
  NarrateResult,
  Page,
  PolicyOut,
  RiskRunOut,
  RulePackOut,
  SampleItemOut,
  SampleSizeWorkpaper,
  TenantSettings,
  TransactionRow,
  UserOut,
} from "./types";

// --- Auth -----------------------------------------------------------------
// No login: this deployment runs as a single fixed user (see
// backend/sampling/auth/dependencies.py). Mirrored here so the UI can
// show a role badge without a network round-trip.

const DEFAULT_CURRENT_USER: CurrentUser = {
  user_id: "00000000-0000-0000-0000-000000000002",
  tenant_id: "00000000-0000-0000-0000-000000000001",
  role: "admin",
  permissions: [
    "read", "upload_datasets", "create_runs", "record_audit_values", "raise_challenges",
    "approve_policies", "approve_rule_packs", "approve_overrides", "sign_off_evaluations",
    "manage_users", "manage_tenant_settings", "manage_llm_config",
  ],
};

export function useCurrentUser() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => Promise.resolve(DEFAULT_CURRENT_USER),
  });
}

// --- Tenant -----------------------------------------------------------------

export function useTenant() {
  return useQuery({ queryKey: ["tenant"], queryFn: () => apiRequest<TenantSettings>("/api/v1/tenant") });
}

export function useUpdateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<TenantSettings>) =>
      apiRequest<TenantSettings>("/api/v1/tenant", { method: "PATCH", body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant"] }),
  });
}

export function useTenantUsers() {
  return useQuery({ queryKey: ["tenant-users"], queryFn: () => apiRequest<Page<UserOut>>("/api/v1/tenant/users") });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: { email: string; role: string; temporary_password: string; full_name?: string }) =>
      apiRequest<UserOut>("/api/v1/tenant/users", { method: "POST", body: req }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-users"] }),
  });
}

export function usePatchUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, patch }: { userId: string; patch: { role?: string; is_active?: boolean } }) =>
      apiRequest<UserOut>(`/api/v1/tenant/users/${userId}`, { method: "PATCH", body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-users"] }),
  });
}

export function useUpdateLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: { llm_enabled: boolean; llm_provider: string | null; llm_model: string | null }) =>
      apiRequest<TenantSettings>("/api/v1/tenant/llm-config", { method: "PUT", body: config }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant"] }),
  });
}

// --- Engagements --------------------------------------------------------

export function useEngagements() {
  return useQuery({ queryKey: ["engagements"], queryFn: () => apiRequest<Page<EngagementOut>>("/api/v1/engagements") });
}

export function useEngagement(id: string | undefined) {
  return useQuery({
    queryKey: ["engagements", id],
    queryFn: () => apiRequest<EngagementOut>(`/api/v1/engagements/${id}`),
    enabled: !!id,
  });
}

export function useCreateEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: { name: string; client_name: string; period_start?: string; period_end?: string; performance_materiality?: number }) =>
      apiRequest<EngagementOut>("/api/v1/engagements", { method: "POST", body: req }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["engagements"] }),
  });
}

// --- Datasets ------------------------------------------------------------

export function useDatasets() {
  return useQuery({ queryKey: ["datasets"], queryFn: () => apiRequest<Page<DatasetOut>>("/api/v1/datasets") });
}

export function useDataset(id: string | undefined, poll = false) {
  return useQuery({
    queryKey: ["datasets", id],
    queryFn: () => apiRequest<DatasetOut>(`/api/v1/datasets/${id}`),
    enabled: !!id,
    refetchInterval: poll ? 2000 : false,
  });
}

export function useDatasetProfile(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id, "profile"],
    queryFn: () => apiRequest<{ schema_profile: Record<string, unknown>; warnings: string[] }>(`/api/v1/datasets/${id}/profile`),
    enabled: !!id,
  });
}

export function useDatasetPreview(id: string | undefined, n = 20) {
  return useQuery({
    queryKey: ["datasets", id, "preview", n],
    queryFn: () => apiRequest<{ rows: Record<string, unknown>[] }>(`/api/v1/datasets/${id}/preview`, { query: { n } }),
    enabled: !!id,
  });
}

export function useUploadDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ engagementId, file }: { engagementId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return apiRequest<DatasetOut>("/api/v1/datasets", {
        method: "POST", isFormData: true, body: form, query: { engagement_id: engagementId },
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });
}

export function useConfirmColumnMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, mapping }: { datasetId: string; mapping: { item_id_col: string; amount_col: string; timestamp_col?: string; entity_col?: string } }) =>
      apiRequest<DatasetOut>(`/api/v1/datasets/${datasetId}/column-mapping`, { method: "PUT", body: mapping }),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["datasets", vars.datasetId] }),
  });
}

export function useSchemaSuggest() {
  return useMutation({
    mutationFn: (datasetId: string) =>
      apiRequest<{ column_roles: Record<string, string>; preprocessing_plan: unknown[]; leakage_candidates: string[]; note: string }>(
        `/api/v1/datasets/${datasetId}/schema-suggest`, { method: "POST" },
      ),
  });
}

// --- Policies --------------------------------------------------------------

export function usePolicies() {
  return useQuery({ queryKey: ["policies"], queryFn: () => apiRequest<Page<PolicyOut>>("/api/v1/policies") });
}

export function useCreatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: Record<string, unknown>) => apiRequest<PolicyOut>("/api/v1/policies", { method: "POST", body: req }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}

export function useApprovePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (policyId: string) => apiRequest<PolicyOut>(`/api/v1/policies/${policyId}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}

export function usePreviewSampleSize(req: {
  book_value: number; tolerable_misstatement: number; expected_misstatement: number;
  confidence_level: number; min_sample_size: number; max_sample_size?: number;
} | null) {
  return useQuery({
    queryKey: ["preview-sample-size", req],
    queryFn: () => apiRequest<SampleSizeWorkpaper>("/api/v1/policies/preview-sample-size", { method: "POST", body: req }),
    enabled: !!req && req.book_value > 0 && req.tolerable_misstatement > 0,
    retry: false,
  });
}

// --- Rule packs --------------------------------------------------------

export function useRulePacks() {
  return useQuery({ queryKey: ["rule-packs"], queryFn: () => apiRequest<Page<RulePackOut>>("/api/v1/rule-packs") });
}

export function useCreateRulePack() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (yamlSource: string) => apiRequest<RulePackOut>("/api/v1/rule-packs", { method: "POST", body: { yaml_source: yamlSource } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rule-packs"] }),
  });
}

export function useValidateRulePack() {
  return useMutation({
    mutationFn: (yamlSource: string) =>
      apiRequest<{ valid: boolean; errors: string[]; pack_id?: string; pack_version?: string; rule_count?: number }>(
        "/api/v1/rule-packs/validate", { method: "POST", body: { yaml_source: yamlSource } },
      ),
  });
}

export function useDryRunRulePack() {
  return useMutation({
    mutationFn: ({ rulePackId, datasetId }: { rulePackId: string; datasetId: string }) =>
      apiRequest<{ hit_counts: Record<string, number>; population_size: number; skipped_rules: string[]; warnings: string[] }>(
        `/api/v1/rule-packs/${rulePackId}/dry-run`, { method: "POST", query: { dataset_id: datasetId } },
      ),
  });
}

export function useApproveRulePack() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest<RulePackOut>(`/api/v1/rule-packs/${id}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rule-packs"] }),
  });
}

// --- Risk runs --------------------------------------------------------

export function useRiskRuns() {
  return useQuery({ queryKey: ["risk-runs"], queryFn: () => apiRequest<Page<RiskRunOut>>("/api/v1/risk-runs") });
}

export function useRiskRun(runId: string | undefined, poll = false) {
  return useQuery({
    queryKey: ["risk-runs", runId],
    queryFn: () => apiRequest<RiskRunOut>(`/api/v1/risk-runs/${runId}`),
    enabled: !!runId,
    refetchInterval: poll ? 1500 : false,
  });
}

export function useCreateRiskRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: Record<string, unknown>) => apiRequest<{ run_id: string; job_id: string; status: string }>("/api/v1/risk-runs", { method: "POST", body: req }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-runs"] }),
  });
}

export function useSample(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "sample"],
    queryFn: () => apiRequest<{ items: SampleItemOut[]; warnings: string[] }>(`/api/v1/risk-runs/${runId}/sample`),
    enabled: !!runId,
  });
}

export function useStrata(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "strata"],
    queryFn: () => apiRequest<{ strata: Record<string, { projectable: boolean; count: number; total_amount: string }> }>(`/api/v1/risk-runs/${runId}/strata`),
    enabled: !!runId,
  });
}

export function useTransactions(runId: string | undefined, params: { sort_by?: string; stratum?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["risk-runs", runId, "transactions", params],
    queryFn: () => apiRequest<Page<TransactionRow>>(`/api/v1/risk-runs/${runId}/transactions`, { query: params }),
    enabled: !!runId,
  });
}

// --- Testing --------------------------------------------------------

export function useSetAuditValue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, itemId, auditValue, note }: { runId: string; itemId: string; auditValue: number; note?: string }) =>
      apiRequest(`/api/v1/risk-runs/${runId}/items/${itemId}/audit-value`, { method: "PUT", body: { audit_value: auditValue, note } }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["risk-runs", vars.runId, "sample"] });
      qc.invalidateQueries({ queryKey: ["risk-runs", vars.runId, "testing-progress"] });
    },
  });
}

export function useTestingProgress(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "testing-progress"],
    queryFn: () => apiRequest<{ total_sample_items: number; tested_count: number; untested_count: number; pct_complete: number }>(
      `/api/v1/risk-runs/${runId}/testing-progress`,
    ),
    enabled: !!runId,
  });
}

export function useEvaluate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, tolerableMisstatement, confidenceLevel }: { runId: string; tolerableMisstatement: number; confidenceLevel: number }) =>
      apiRequest<{ evaluation_id: string; workpaper: EvaluationWorkpaper }>(`/api/v1/risk-runs/${runId}/evaluate`, {
        method: "POST", query: { tolerable_misstatement: tolerableMisstatement, confidence_level: confidenceLevel },
      }),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["risk-runs", vars.runId, "evaluation"] }),
  });
}

export function useEvaluation(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "evaluation"],
    queryFn: () => apiRequest<{ evaluation_id: string; workpaper: EvaluationWorkpaper; conclusion: string; signed_off_by: string | null }>(
      `/api/v1/risk-runs/${runId}/evaluation`,
    ),
    enabled: !!runId,
    retry: false,
  });
}

export function useSignOffEvaluation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, evaluationId }: { runId: string; evaluationId: string }) =>
      apiRequest(`/api/v1/risk-runs/${runId}/evaluation/sign-off`, { method: "POST", body: { evaluation_id: evaluationId } }),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["risk-runs", vars.runId, "evaluation"] }),
  });
}

// --- Challenge --------------------------------------------------------

export function useExplanation(runId: string | undefined, itemId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "items", itemId, "explanation"],
    queryFn: () => apiRequest<EvidenceOut>(`/api/v1/risk-runs/${runId}/items/${itemId}/explanation`),
    enabled: !!runId && !!itemId,
  });
}

export function useNarrate() {
  return useMutation({
    mutationFn: ({ runId, itemId, question }: { runId: string; itemId: string; question?: string }) =>
      apiRequest<NarrateResult>(`/api/v1/risk-runs/${runId}/items/${itemId}/narrate`, { method: "POST", query: { question } }),
  });
}

export function useCompare(runId: string | undefined, itemA: string | undefined, itemB: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "compare", itemA, itemB],
    queryFn: () => apiRequest<{ item_a: EvidenceOut; item_b: EvidenceOut; rules_only_in_a: string[]; rules_only_in_b: string[]; rules_in_both: string[]; amount_difference: number }>(
      `/api/v1/risk-runs/${runId}/compare`, { query: { item_a: itemA, item_b: itemB } },
    ),
    enabled: !!runId && !!itemA && !!itemB,
  });
}

export function useCreateOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, itemId, action, reason }: { runId: string; itemId: string; action: string; reason: string }) =>
      apiRequest<{ override_id: string; note: string }>(`/api/v1/risk-runs/${runId}/override`, {
        method: "POST", body: { item_id: itemId, action, reason },
      }),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["risk-runs", vars.runId, "overrides"] }),
  });
}

export function useOverrides(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "overrides"],
    queryFn: () => apiRequest<{ items: Array<{ id: string; item_id: string; action: string; reason: string; approved_by: string | null }> }>(
      `/api/v1/risk-runs/${runId}/overrides`,
    ),
    enabled: !!runId,
  });
}

// --- Benchmark --------------------------------------------------------

export function useBenchmark(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "benchmark"],
    queryFn: () => apiRequest<{ verdict: BenchmarkVerdict; report: BenchmarkReport }>(`/api/v1/risk-runs/${runId}/benchmark`),
    enabled: !!runId,
    retry: false,
  });
}

// --- Evidence --------------------------------------------------------

export function useEvidencePack(runId: string | undefined) {
  return useQuery({
    queryKey: ["risk-runs", runId, "evidence-pack"],
    queryFn: () => apiRequest<Record<string, unknown>>(`/api/v1/risk-runs/${runId}/evidence-pack`),
    enabled: !!runId,
  });
}

// --- Audit trail --------------------------------------------------------

export function useAuditEvents(params: { subject?: string; actor?: string; action?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["audit-events", params],
    queryFn: () => apiRequest<Page<AuditEventOut>>("/api/v1/audit-events", { query: params }),
  });
}

export function useVerifyAuditTrail() {
  return useMutation({
    mutationFn: () => apiRequest<{ valid: boolean; first_invalid_sequence: number | null; reason: string | null; events_checked: number }>(
      "/api/v1/audit-events/verify",
    ),
  });
}
