import { Calculator } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useCreatePolicy, useEngagements, usePreviewSampleSize } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { errorMessage, toast } from "../stores/toastStore";

export function PolicyEditor() {
  const { data: engagements } = useEngagements();
  const [engagementId, setEngagementId] = useState("");
  const [policyVersion, setPolicyVersion] = useState("v1");
  const [bookValue, setBookValue] = useState(1_000_000);
  const [tolerableMisstatement, setTolerableMisstatement] = useState(50_000);
  const [expectedMisstatement, setExpectedMisstatement] = useState(0);
  const [confidenceLevel, setConfidenceLevel] = useState(0.95);
  const [randomControlSize, setRandomControlSize] = useState(20);
  const [highRiskThreshold, setHighRiskThreshold] = useState(90);
  const create = useCreatePolicy();
  const navigate = useNavigate();

  const preview = usePreviewSampleSize({
    book_value: bookValue, tolerable_misstatement: tolerableMisstatement,
    expected_misstatement: expectedMisstatement, confidence_level: confidenceLevel,
    min_sample_size: 0,
  });

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const policy = await create.mutateAsync({
        engagement_id: engagementId, policy_version: policyVersion,
        tolerable_misstatement: tolerableMisstatement, expected_misstatement: expectedMisstatement,
        confidence_level: confidenceLevel, random_control_size: randomControlSize,
        high_risk_threshold: highRiskThreshold,
      });
      toast.success(`Policy ${policyVersion} created.`);
      navigate(`/runs/launch?policy_id=${policy.id}&engagement_id=${engagementId}`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not create policy"));
    }
  };

  return (
    <div className="grid grid-cols-2 gap-6">
      <div>
        <PageHeader title="New sampling policy" description="Materiality, confidence, and stratification for a risk run." />
        <Card className="p-5">
          <form onSubmit={onSubmit} className="space-y-4">
            <Field label="Engagement">
              <select required value={engagementId} onChange={(e) => setEngagementId(e.target.value)} className="input w-full">
                <option value="">Select...</option>
                {(engagements?.items ?? []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
            </Field>

            <Field label="Policy version">
              <input value={policyVersion} onChange={(e) => setPolicyVersion(e.target.value)} className="input w-full" />
            </Field>

            <Field label="Population book value (for preview only)">
              <input type="number" value={bookValue} onChange={(e) => setBookValue(Number(e.target.value))} className="input w-full" />
            </Field>

            <Field label="Tolerable misstatement">
              <input type="number" value={tolerableMisstatement} onChange={(e) => setTolerableMisstatement(Number(e.target.value))} className="input w-full" />
            </Field>

            <Field label="Expected misstatement">
              <input type="number" value={expectedMisstatement} onChange={(e) => setExpectedMisstatement(Number(e.target.value))} className="input w-full" />
            </Field>

            <Field label="Confidence level">
              <select value={confidenceLevel} onChange={(e) => setConfidenceLevel(Number(e.target.value))} className="input w-full">
                {[0.80, 0.85, 0.90, 0.95, 0.99].map((c) => <option key={c} value={c}>{(c * 100).toFixed(0)}%</option>)}
              </select>
            </Field>

            <Field label="Random control stratum size">
              <input type="number" value={randomControlSize} onChange={(e) => setRandomControlSize(Number(e.target.value))} className="input w-full" />
            </Field>

            <Field label="High-risk threshold (0-100)">
              <input type="number" value={highRiskThreshold} onChange={(e) => setHighRiskThreshold(Number(e.target.value))} className="input w-full" />
            </Field>

            <Button type="submit" variant="primary" loading={create.isPending} disabled={!engagementId} className="w-full justify-center">
              Create policy
            </Button>
          </form>
        </Card>
      </div>

      <div className="sticky top-8 h-fit">
        <Card>
          <CardHeader title={<span className="flex items-center gap-2"><Calculator size={16} /> Live sample size preview</span>} />
          <div className="p-5">
            {preview.isError && (
              <div className="warning-banner">
                {preview.error instanceof ApiError ? preview.error.message : "Could not compute sample size"}
              </div>
            )}
            {preview.data && (
              <dl className="text-sm space-y-2">
                <Row label="Book value" value={preview.data.book_value.toLocaleString()} />
                <Row label="Reliability factor (RF)" value={preview.data.reliability_factor.toFixed(4)} />
                <Row label="Expansion factor (EF)" value={preview.data.expansion_factor.toFixed(4)} />
                <Row label="Adjusted tolerable" value={preview.data.adjusted_tolerable.toLocaleString()} />
                <div className="flex justify-between items-center py-2 border-t border-b" style={{ borderColor: "var(--hairline)" }}>
                  <dt style={{ color: "var(--ink-secondary)" }}>Sample size (n)</dt>
                  <dd className="text-2xl font-semibold tabular" style={{ color: "var(--accent)" }}>{preview.data.sample_size}</dd>
                </div>
                <Row label="Sampling interval" value={preview.data.sampling_interval.toLocaleString()} />
                <div className="text-xs pt-2" style={{ color: "var(--ink-muted)" }}>{preview.data.basis}</div>
              </dl>
            )}
          </div>
        </Card>
      </div>
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

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between">
      <dt style={{ color: "var(--ink-secondary)" }}>{label}</dt>
      <dd style={{ color: "var(--ink-primary)" }}>{value}</dd>
    </div>
  );
}
