import { CheckCircle2, PlayCircle, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useApproveRulePack, useCreateRulePack, useDatasets, useDryRunRulePack, useRulePacks, useValidateRulePack } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { errorMessage, toast } from "../stores/toastStore";

const TEMPLATE = `pack_id: my_pack
pack_version: "1.0.0"
rules:
  - rule_id: example_rule
    description: Amount exceeds threshold
    expression: "amount > 10000"
    severity: high
    owner: your-team
    explanation: Large payments warrant review.
    effective_from: "2024-01-01"
    required_columns: [amount]
`;

export function RulePackEditor() {
  const [yamlSource, setYamlSource] = useState(TEMPLATE);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);

  const { data: rulePacks } = useRulePacks();
  const { data: datasets } = useDatasets();
  const validate = useValidateRulePack();
  const create = useCreateRulePack();
  const dryRun = useDryRunRulePack();
  const approve = useApproveRulePack();

  const onValidate = () => validate.mutate(yamlSource);
  const onSave = async () => {
    const result = await validate.mutateAsync(yamlSource);
    if (!result.valid) {
      toast.error("Fix validation errors before saving.");
      return;
    }
    try {
      const saved = await create.mutateAsync(yamlSource);
      setSelectedPackId(saved.id);
      toast.success(`Rule pack ${saved.pack_id} v${saved.pack_version} saved.`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not save rule pack"));
    }
  };
  const onDryRun = () => {
    if (selectedPackId && selectedDatasetId) dryRun.mutate({ rulePackId: selectedPackId, datasetId: selectedDatasetId });
  };
  const onApprove = (id: string) => {
    approve.mutate(id, {
      onSuccess: () => toast.success("Rule pack approved."),
      onError: (err) => toast.error(errorMessage(err, "Approval failed")),
    });
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Rule pack editor" description="Versioned, effective-dated rules with per-rule dry-run hit counts." />

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-3">
          <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
            Effective dating (effective_from / effective_to) lives in the YAML itself and is applied at
            evaluation time -- a superseded rule stops firing after its effective_to date without
            deleting its history. Version diffing against a previous pack version is not implemented
            in this build.
          </p>
          <Card className="p-0 overflow-hidden">
            <textarea
              value={yamlSource} onChange={(e) => setYamlSource(e.target.value)}
              className="w-full h-96 font-mono text-sm p-4 outline-none"
              style={{ background: "var(--surface)", color: "var(--ink-primary)" }}
              spellCheck={false}
            />
          </Card>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onValidate} loading={validate.isPending}>
              <ShieldCheck size={14} /> Validate
            </Button>
            <Button variant="primary" onClick={onSave} loading={create.isPending}>Save</Button>
          </div>
          {validate.data && (
            validate.data.valid ? (
              <div className="text-sm flex items-center gap-2" style={{ color: "var(--status-good)" }}>
                <CheckCircle2 size={16} /> Valid: {validate.data.pack_id} v{validate.data.pack_version}, {validate.data.rule_count} rule(s)
              </div>
            ) : (
              <div className="warning-banner">
                {validate.data.errors.map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Existing rule packs" />
            <CardBody className="p-0">
              {(rulePacks?.items.length ?? 0) === 0 ? (
                <EmptyState icon={ShieldCheck} title="No rule packs yet" description="Save one on the left to get started." />
              ) : (
                <ul>
                  {(rulePacks?.items ?? []).map((rp) => (
                    <li key={rp.id} className="px-5 py-3 border-b last:border-0 flex justify-between items-center" style={{ borderColor: "var(--hairline)" }}>
                      <button className="text-left text-sm font-medium hover:underline" style={{ color: "var(--ink-primary)" }} onClick={() => setSelectedPackId(rp.id)}>
                        {rp.pack_id} v{rp.pack_version}
                      </button>
                      {rp.approved_by ? (
                        <span className="badge" style={{ background: "#e8f8e8", color: "var(--status-good)" }}>approved</span>
                      ) : (
                        <button className="text-xs underline" style={{ color: "var(--accent)" }} onClick={() => onApprove(rp.id)}>approve</button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Dry-run hit counts" />
            <CardBody className="space-y-3">
              <div className="flex gap-2">
                <select value={selectedDatasetId} onChange={(e) => setSelectedDatasetId(e.target.value)} className="input flex-1 text-sm">
                  <option value="">Select a dataset...</option>
                  {(datasets?.items ?? []).map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
                </select>
                <Button variant="secondary" onClick={onDryRun} disabled={!selectedPackId || !selectedDatasetId} loading={dryRun.isPending}>
                  <PlayCircle size={14} /> Run
                </Button>
              </div>
              {!selectedPackId && <p className="text-xs" style={{ color: "var(--ink-muted)" }}>Select a saved rule pack above first.</p>}
              {dryRun.data && (
                <div className="text-sm space-y-1.5">
                  <div style={{ color: "var(--ink-muted)" }}>Population: {dryRun.data.population_size} rows</div>
                  {Object.entries(dryRun.data.hit_counts).map(([ruleId, count]) => (
                    <div key={ruleId} className="flex justify-between">
                      <span style={{ color: "var(--ink-secondary)" }}>{ruleId}</span>
                      <span className="font-medium tabular" style={{ color: "var(--ink-primary)" }}>{count}</span>
                    </div>
                  ))}
                  {dryRun.data.skipped_rules.length > 0 && (
                    <div className="warning-banner mt-2">
                      Skipped (coverage gap, not a clean result): {dryRun.data.skipped_rules.join(", ")}
                    </div>
                  )}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
