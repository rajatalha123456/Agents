import { AlertTriangle } from "lucide-react";
import { useParams } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { useRiskRun, useStrata, useTransactions } from "../api/hooks";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Money } from "../components/Money";
import { RunSubNav } from "../components/RunSubNav";

export function RiskDashboard() {
  const { runId } = useParams();
  const { data: run } = useRiskRun(runId);
  const { data: strata } = useStrata(runId);
  const { data: transactions } = useTransactions(runId, { limit: 500, sort_by: "risk_score" });

  const formulaVersion = run?.risk_manifest?.formula_version ?? "unknown";
  const isUnvalidated = formulaVersion.includes("UNVALIDATED");

  // Score distribution as a coarse histogram over the fetched page.
  const buckets = Array.from({ length: 10 }, (_, i) => ({ range: `${i * 10}-${i * 10 + 9}`, count: 0 }));
  for (const t of transactions?.items ?? []) {
    if (t.risk_score === null) continue;
    const idx = Math.min(9, Math.floor(t.risk_score / 10));
    buckets[idx].count += 1;
  }

  return (
    <div className="space-y-5">
      {/* This banner is deliberately not dismissible -- it stays until the
          formula is validated (section 0.7), never hidden to make a demo
          look better. */}
      {isUnvalidated && (
        <div className="unvalidated-banner flex gap-2">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" color="var(--status-critical)" />
          <div>
            Risk formula version <code>{formulaVersion}</code> is UNVALIDATED. These weights are
            initialisation defaults, not data-derived, and must not be presented as a validated risk
            assessment. This tag is removed only after a benchmark on real engagement data with 30+
            confirmed findings returns BEATS_RANDOM.
          </div>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Risk dashboard</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      <Card>
        <CardHeader title="Risk score distribution (sampled page)" />
        <CardBody>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={buckets}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
              <XAxis dataKey="range" fontSize={11} stroke="var(--ink-muted)" />
              <YAxis fontSize={11} stroke="var(--ink-muted)" />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" fill="var(--series-blue)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Stratum breakdown" />
        <CardBody className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left" style={{ color: "var(--ink-muted)" }}>
                <th className="px-5 py-2 font-medium">Stratum</th>
                <th className="px-5 py-2 font-medium">Projectable</th>
                <th className="px-5 py-2 font-medium">Items</th>
                <th className="px-5 py-2 font-medium">Total amount</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(strata?.strata ?? {}).map(([name, s]) => (
                <tr key={name} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                  <td className="px-5 py-2.5" style={{ color: "var(--ink-primary)" }}>{name}</td>
                  <td className="px-5 py-2.5">
                    <span className="badge" style={{ background: s.projectable ? "#e8f1fc" : "#fdece4", color: s.projectable ? "var(--series-blue)" : "var(--series-orange)" }}>
                      {s.projectable ? "statistical" : "judgmental"}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 tabular" style={{ color: "var(--ink-primary)" }}>{s.count}</td>
                  <td className="px-5 py-2.5"><Money value={s.total_amount} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <CardHeader title="Rule pack" />
          <CardBody>
            <pre className="text-xs overflow-x-auto" style={{ color: "var(--ink-secondary)" }}>{JSON.stringify(run?.rules_manifest, null, 2)}</pre>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Anomaly manifest" />
          <CardBody>
            <pre className="text-xs overflow-x-auto" style={{ color: "var(--ink-secondary)" }}>{JSON.stringify(run?.anomaly_manifest, null, 2)}</pre>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
