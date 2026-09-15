import { useState } from "react";
import { useParams } from "react-router-dom";
import { useEvaluate, useEvaluation, useSignOffEvaluation } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { RunSubNav } from "../components/RunSubNav";
import { Warnings } from "../components/Warnings";
import { errorMessage, toast } from "../stores/toastStore";

const VERDICT_STYLE: Record<string, { bg: string; border: string }> = {
  ACCEPT: { bg: "color-mix(in srgb, var(--status-good) 12%, var(--surface))", border: "var(--status-good)" },
  REJECT: { bg: "color-mix(in srgb, var(--status-critical) 10%, var(--surface))", border: "var(--status-critical)" },
  INCONCLUSIVE: { bg: "color-mix(in srgb, var(--status-warning) 15%, var(--surface))", border: "var(--status-warning)" },
};

export function Evaluation() {
  const { runId } = useParams();
  const [tolerableMisstatement, setTolerableMisstatement] = useState(50000);
  const evaluate = useEvaluate();
  const { data: evaluation } = useEvaluation(runId);
  const signOff = useSignOffEvaluation();

  const workpaper = evaluation?.workpaper;

  const onEvaluate = () => {
    if (!runId) return;
    evaluate.mutate({ runId, tolerableMisstatement, confidenceLevel: 0.95 }, {
      onSuccess: (r) => toast.success(`Evaluation complete: ${r.workpaper.conclusion}`),
      onError: (err) => toast.error(errorMessage(err, "Evaluation failed")),
    });
  };

  const onSignOff = () => {
    if (!runId || !evaluation) return;
    signOff.mutate({ runId, evaluationId: evaluation.evaluation_id }, {
      onSuccess: () => toast.success("Evaluation signed off."),
      onError: (err) => toast.error(errorMessage(err, "Sign-off failed")),
    });
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Evaluation</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      <Card className="p-5 flex items-end gap-3">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Tolerable misstatement</label>
          <input type="number" value={tolerableMisstatement} onChange={(e) => setTolerableMisstatement(Number(e.target.value))} className="input" />
        </div>
        <Button variant="primary" onClick={onEvaluate} loading={evaluate.isPending}>Run evaluation</Button>
      </Card>

      {workpaper && (
        <>
          <div className="rounded-xl p-5" style={{ background: VERDICT_STYLE[workpaper.conclusion]?.bg, border: `2px solid ${VERDICT_STYLE[workpaper.conclusion]?.border}` }}>
            <div className="text-2xl font-bold" style={{ color: "var(--ink-primary)" }}>{workpaper.conclusion}</div>
            <p className="text-sm mt-1" style={{ color: "var(--ink-secondary)" }}>{workpaper.conclusion_basis}</p>
          </div>

          <Warnings warnings={workpaper.warnings} />

          <Card>
            <CardHeader title="Overstatement workpaper" />
            <CardBody>
              <dl className="text-sm space-y-1.5">
                <Row label="Known misstatement" value={workpaper.known_misstatement} />
                <Row label="Projected misstatement" value={workpaper.projected_misstatement} />
                <Row label="Most likely misstatement (MLM)" value={workpaper.most_likely_misstatement} />
                <Row label="Basic precision" value={workpaper.basic_precision} />
                <Row label="Incremental allowance" value={workpaper.incremental_allowance} />
                <Row label="Allowance for sampling risk" value={workpaper.allowance_for_sampling_risk} />
                <Row label="Upper misstatement limit (UML)" value={workpaper.upper_misstatement_limit} bold />
                <Row label="Tolerable misstatement" value={workpaper.tolerable_misstatement} />
                <Row label="Judgmental known misstatement" value={workpaper.judgmental_known_misstatement} />
              </dl>
            </CardBody>
          </Card>

          {/* Understatement is never netted into the overstatement figures
              above -- it gets its own section, always. */}
          <div className="app-card p-5" style={{ borderLeft: "3px solid var(--series-violet)" }}>
            <h2 className="font-semibold text-sm mb-1" style={{ color: "var(--ink-primary)" }}>Understatement (never netted against overstatement)</h2>
            <p className="text-sm" style={{ color: "var(--ink-secondary)" }}>
              Projected understatement: <span className="font-medium tabular" style={{ color: "var(--ink-primary)" }}>{workpaper.projected_understatement.toLocaleString()}</span>
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--ink-muted)" }}>
              MUS is biased toward overstatements by design; understatement is tracked separately and
              netting it against the figures above would hide a completeness gap.
            </p>
          </div>

          <Card className="p-5 flex items-center justify-between">
            <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>
              Signed off by: {evaluation?.signed_off_by ?? <span style={{ color: "var(--status-warning)" }}>not yet signed off</span>}
            </div>
            {!evaluation?.signed_off_by && (
              <Button variant="secondary" onClick={onSignOff} loading={signOff.isPending}>
                Sign off (requires a second reviewer)
              </Button>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: number; bold?: boolean }) {
  return (
    <div className="flex justify-between" style={bold ? { fontWeight: 600, borderTop: "1px solid var(--hairline)", paddingTop: "0.4rem" } : undefined}>
      <dt style={{ color: "var(--ink-secondary)" }}>{label}</dt>
      <dd className="tabular" style={{ color: "var(--ink-primary)" }}>{value.toLocaleString()}</dd>
    </div>
  );
}
