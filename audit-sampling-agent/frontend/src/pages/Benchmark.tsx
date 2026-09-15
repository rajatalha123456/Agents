import { BarChart3 } from "lucide-react";
import { useParams } from "react-router-dom";
import { useBenchmark } from "../api/hooks";
import { Card, CardBody } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { RunSubNav } from "../components/RunSubNav";
import { Warnings } from "../components/Warnings";

const VERDICT_TEXT: Record<string, { bg: string; border: string; plain: string }> = {
  BEATS_RANDOM: { bg: "color-mix(in srgb, var(--status-good) 12%, var(--surface))", border: "var(--status-good)", plain: "This ranking beats random selection with statistical confidence." },
  WORSE_THAN_RANDOM: { bg: "color-mix(in srgb, var(--status-critical) 10%, var(--surface))", border: "var(--status-critical)", plain: "This ranking performs worse than random -- check for inverted scoring or label leakage." },
  NOT_DISTINGUISHABLE_FROM_RANDOM: { bg: "color-mix(in srgb, var(--status-warning) 15%, var(--surface))", border: "var(--status-warning)", plain: "This ranking cannot be distinguished from random selection given the available data. It has not been shown to work." },
  INSUFFICIENT_DATA: { bg: "color-mix(in srgb, var(--ink-muted) 12%, var(--surface))", border: "var(--ink-muted)", plain: "There are not enough confirmed findings yet to draw any conclusion, regardless of how the lift number looks." },
};

export function Benchmark() {
  const { runId } = useParams();
  const { data, isError } = useBenchmark(runId);

  if (isError) {
    return (
      <div className="max-w-xl space-y-5">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Benchmark</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
        </div>
        <RunSubNav runId={runId!} />
        <Card>
          <CardBody className="p-0">
            <EmptyState icon={BarChart3} title="No benchmark yet" description="Run one against confirmed findings to see precision, recall, and lift." />
          </CardBody>
        </Card>
      </div>
    );
  }
  if (!data) return <div style={{ color: "var(--ink-muted)" }}>Loading...</div>;

  const verdictInfo = VERDICT_TEXT[data.verdict];

  return (
    <div className="max-w-xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Benchmark</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      <div className="rounded-xl p-5" style={{ background: verdictInfo.bg, border: `2px solid ${verdictInfo.border}` }}>
        <div className="text-xl font-bold" style={{ color: "var(--ink-primary)" }}>{data.verdict}</div>
        <p className="text-sm mt-1" style={{ color: "var(--ink-secondary)" }}>{verdictInfo.plain}</p>
      </div>

      <Warnings warnings={data.report.warnings} />

      <Card className="p-5">
        <dl className="text-sm space-y-2">
          <Row label="Precision@K" value={`${(data.report.precision * 100).toFixed(1)}%`} />
          <Row label="Recall@K" value={`${(data.report.recall * 100).toFixed(1)}%`} />
          <Row label="Base rate" value={`${(data.report.base_rate * 100).toFixed(1)}%`} />
          {/* The lift point estimate is never shown without its interval. */}
          <Row
            label="Lift (95% CI)"
            value={`${data.report.lift.toFixed(2)}x  [${data.report.lift_ci_low.toFixed(2)}, ${data.report.lift_ci_high.toFixed(2)}]`}
          />
          <Row label="Confirmed findings (K)" value={`${data.report.k} of ${data.report.n}`} />
        </dl>
        <p className="text-sm mt-4 pt-3 border-t" style={{ borderColor: "var(--hairline)", color: "var(--ink-secondary)" }}>{data.report.statement}</p>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt style={{ color: "var(--ink-secondary)" }}>{label}</dt>
      <dd className="font-medium tabular" style={{ color: "var(--ink-primary)" }}>{value}</dd>
    </div>
  );
}
