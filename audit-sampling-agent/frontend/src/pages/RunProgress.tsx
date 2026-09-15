import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useRiskRun } from "../api/hooks";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { Skeleton } from "../components/ui/Skeleton";
import { Warnings } from "../components/Warnings";

const STAGES = [
  { pct: 10, label: "Population loaded" },
  { pct: 25, label: "Risk flags added" },
  { pct: 45, label: "Rules evaluated" },
  { pct: 70, label: "Anomaly detection scored" },
  { pct: 90, label: "Sample built" },
  { pct: 100, label: "Complete" },
];

export function RunProgress() {
  const { runId } = useParams();
  const isTerminal = (status?: string) => status === "complete" || status === "failed" || status === "cancelled";
  const { data: run } = useRiskRun(runId, true);
  const navigate = useNavigate();

  useEffect(() => {
    if (run?.status === "complete") {
      navigate(`/runs/${run.run_id}/sample`);
    }
  }, [run?.status, run?.run_id, navigate]);

  if (!run) {
    return (
      <div className="max-w-xl space-y-4">
        <Skeleton className="h-8 w-56" />
        <Card className="p-5 space-y-3"><Skeleton className="h-3 w-full" /><Skeleton className="h-24 w-full" /></Card>
      </div>
    );
  }

  return (
    <div className="max-w-xl space-y-5">
      <PageHeader title={`Run progress`} description={run.run_id} />
      <Card className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm capitalize font-medium" style={{ color: "var(--ink-secondary)" }}>Status: {run.status}</span>
          {!isTerminal(run.status) && <Loader2 size={16} className="animate-spin" color="var(--series-blue)" />}
        </div>
        <div className="w-full rounded-full h-2.5" style={{ background: "var(--hairline)" }}>
          <div
            className="h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${run.progress_pct}%`, background: run.status === "failed" ? "var(--status-critical)" : "var(--series-blue)" }}
          />
        </div>
        <ul className="text-sm space-y-2">
          {STAGES.map((s) => {
            const done = run.progress_pct >= s.pct;
            return (
              <li key={s.pct} className="flex items-center gap-2" style={{ color: done ? "var(--ink-primary)" : "var(--ink-muted)" }}>
                {done ? <CheckCircle2 size={15} color="var(--status-good)" /> : <Circle size={15} />}
                {s.label}
              </li>
            );
          })}
        </ul>
        {run.status === "failed" && (
          <div className="warning-banner">Run failed: {run.error_message}</div>
        )}
        {!isTerminal(run.status) && <div className="text-xs" style={{ color: "var(--ink-muted)" }}>Polling every 1.5s...</div>}
      </Card>
      <Warnings warnings={run.warnings} />
    </div>
  );
}
