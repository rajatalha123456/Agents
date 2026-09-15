import { PlayCircle, Rocket } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useCreateRiskRun, useDatasets, useEngagements, usePolicies, useRulePacks } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { errorMessage, toast } from "../stores/toastStore";

export function RunLauncher() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const { data: engagements } = useEngagements();
  const { data: datasets } = useDatasets();
  const { data: policies } = usePolicies();
  const { data: rulePacks } = useRulePacks();
  const create = useCreateRiskRun();

  const [engagementId, setEngagementId] = useState(params.get("engagement_id") ?? "");
  const [datasetId, setDatasetId] = useState("");
  const [policyId, setPolicyId] = useState(params.get("policy_id") ?? "");
  const [rulePackId, setRulePackId] = useState("");
  const [seed, setSeed] = useState("");
  const [runId, setRunId] = useState(`run-${Date.now()}`);
  const [confirmed, setConfirmed] = useState(false);

  const selectedDataset = datasets?.items.find((d) => d.id === datasetId);
  const selectedPolicy = policies?.items.find((p) => p.id === policyId);
  const selectedRulePack = rulePacks?.items.find((r) => r.id === rulePackId);

  const onLaunch = async () => {
    try {
      const result = await create.mutateAsync({
        engagement_id: engagementId, dataset_id: datasetId, policy_id: policyId,
        rule_pack_id: rulePackId || undefined, user_seed: seed || undefined, run_id: runId,
      });
      toast.success(`Run ${result.run_id} launched.`);
      navigate(`/runs/${result.run_id}/progress`);
    } catch (err) {
      toast.error(errorMessage(err, "Failed to launch run"));
    }
  };

  return (
    <div className="max-w-xl space-y-5">
      <PageHeader title="Launch a risk run" description="Pick a dataset, policy, and optional rule pack, then confirm before launching." />

      <Card className="p-5 space-y-4">
        <Field label="Engagement">
          <select value={engagementId} onChange={(e) => setEngagementId(e.target.value)} className="input w-full">
            <option value="">Select...</option>
            {(engagements?.items ?? []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </Field>

        <Field label="Dataset (must be fully ingested)">
          <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} className="input w-full">
            <option value="">Select...</option>
            {(datasets?.items ?? []).filter((d) => d.ingestion_status === "complete").map((d) => (
              <option key={d.id} value={d.id}>{d.filename} ({d.row_count} rows)</option>
            ))}
          </select>
        </Field>

        <Field label="Sampling policy">
          <select value={policyId} onChange={(e) => setPolicyId(e.target.value)} className="input w-full">
            <option value="">Select...</option>
            {(policies?.items ?? []).map((p) => <option key={p.id} value={p.id}>{p.policy_version}</option>)}
          </select>
        </Field>

        <Field label="Rule pack (optional)">
          <select value={rulePackId} onChange={(e) => setRulePackId(e.target.value)} className="input w-full">
            <option value="">None</option>
            {(rulePacks?.items ?? []).map((r) => <option key={r.id} value={r.id}>{r.pack_id} v{r.pack_version}</option>)}
          </select>
        </Field>

        <Field label="Seed (optional -- leave blank for a random draw)">
          <input value={seed} onChange={(e) => setSeed(e.target.value)} className="input w-full" />
        </Field>

        <Field label="Run ID">
          <input value={runId} onChange={(e) => setRunId(e.target.value)} className="input w-full" />
        </Field>
      </Card>

      {!confirmed ? (
        <Button variant="primary" disabled={!engagementId || !datasetId || !policyId} onClick={() => setConfirmed(true)}>
          <PlayCircle size={16} /> Review before launching
        </Button>
      ) : (
        <Card className="p-5 space-y-3">
          <h2 className="font-semibold text-sm" style={{ color: "var(--ink-primary)" }}>Exactly what will run</h2>
          <dl className="text-sm space-y-1.5">
            <Row label="Dataset" value={selectedDataset?.filename ?? "—"} />
            <Row label="Policy" value={selectedPolicy?.policy_version ?? "—"} />
            <Row label="Rule pack" value={selectedRulePack ? `${selectedRulePack.pack_id} v${selectedRulePack.pack_version}` : "none"} />
            <Row label="Seed" value={seed || "(random)"} />
            <Row label="Run ID" value={runId} />
          </dl>
          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={() => setConfirmed(false)}>Back</Button>
            <Button variant="primary" onClick={onLaunch} loading={create.isPending}>
              <Rocket size={14} /> Launch run
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--ink-primary)" }}>{label}</label>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt style={{ color: "var(--ink-secondary)" }}>{label}</dt>
      <dd className="font-medium" style={{ color: "var(--ink-primary)" }}>{value}</dd>
    </div>
  );
}
