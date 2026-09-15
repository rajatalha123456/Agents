import {
  Area, AreaChart, Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowRight, Briefcase, CheckCircle2, Circle, Database, FileStack, FolderPlus, Info,
  PlayCircle, ShieldCheck, Sparkles, Upload,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  useAuditEvents, useCurrentUser, useDatasets, useEngagements, usePolicies, useRiskRuns,
} from "../api/hooks";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { StatTile } from "../components/ui/StatTile";
import { StatusBadge } from "../components/ui/StatusBadge";
import { formatDateTime } from "../lib/dates";

const STATUS_COLOR: Record<string, string> = {
  complete: "var(--status-good)",
  running: "var(--series-blue)",
  queued: "var(--status-warning)",
  failed: "var(--status-critical)",
  cancelled: "var(--ink-muted)",
};

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export function Dashboard() {
  const { data: user } = useCurrentUser();
  const { data: engagements } = useEngagements();
  const { data: datasets } = useDatasets();
  const { data: policies } = usePolicies();
  const { data: runs } = useRiskRuns();
  const { data: recentEvents } = useAuditEvents({ limit: 6 });
  const { data: activityEvents } = useAuditEvents({ limit: 300 });

  const byStatus = (runs?.items ?? []).reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});
  const statusChartData = Object.entries(byStatus).map(([status, count]) => ({ name: status, value: count }));
  const completeCount = byStatus.complete ?? 0;

  // Getting-started checklist -- computed from real data, not a static list.
  const hasEngagement = (engagements?.total ?? 0) > 0;
  const hasDataset = (datasets?.items ?? []).some((d) => d.ingestion_status === "complete");
  const hasPolicy = (policies?.total ?? 0) > 0;
  const hasRun = (runs?.total ?? 0) > 0;
  const steps = [
    { done: hasEngagement, label: "Create an engagement", to: "/engagements", icon: FolderPlus },
    { done: hasDataset, label: "Upload and ingest a dataset", to: "/datasets/upload", icon: Upload },
    { done: hasPolicy, label: "Set a sampling policy", to: "/policies/new", icon: ShieldCheck },
    { done: hasRun, label: "Launch a risk run", to: "/runs/launch", icon: PlayCircle },
  ];
  const allDone = steps.every((s) => s.done);

  // Dataset size chart -- rows ingested per dataset (top 6 by row count).
  const datasetChartData = (datasets?.items ?? [])
    .filter((d) => d.row_count !== null)
    .sort((a, b) => (b.row_count ?? 0) - (a.row_count ?? 0))
    .slice(0, 6)
    .map((d) => ({ name: d.filename.length > 14 ? d.filename.slice(0, 12) + "…" : d.filename, rows: d.row_count ?? 0 }));

  // Activity-over-time chart -- audit events bucketed by day, last 7 days.
  const dayBuckets: { date: string; label: string; count: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    dayBuckets.push({ date: key, label: d.toLocaleDateString(undefined, { weekday: "short" }), count: 0 });
  }
  for (const ev of activityEvents?.items ?? []) {
    const key = ev.timestamp.slice(0, 10);
    const bucket = dayBuckets.find((b) => b.date === key);
    if (bucket) bucket.count += 1;
  }

  const greetingRole = user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : "";

  return (
    <div className="space-y-6">
      {/* Welcome hero */}
      <div className="rounded-2xl p-6" style={{ background: "linear-gradient(135deg, var(--series-blue), var(--series-violet))" }}>
        <h1 className="text-2xl font-semibold text-white">{greeting()}{greetingRole ? `, ${greetingRole}` : ""} 👋</h1>
        <p className="text-sm mt-1 text-white/85 max-w-xl">
          This is your ISA 530 sampling workspace: upload a population, set a materiality-based policy, draw a
          statistically defensible sample, and track every decision through a tamper-evident audit trail.
        </p>
      </div>

      {/* Getting started checklist -- only shown until every step is done */}
      {!allDone && (
        <Card className="p-5" style={{ borderColor: "var(--accent)" }}>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={16} color="var(--accent)" />
            <h2 className="font-semibold text-sm" style={{ color: "var(--ink-primary)" }}>Get started in 4 steps</h2>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {steps.map((s) => {
              const Icon = s.icon;
              return (
                <Link
                  key={s.label}
                  to={s.to}
                  className="rounded-xl p-3.5 flex flex-col gap-2 transition-colors"
                  style={{
                    border: `1px solid ${s.done ? "var(--status-good)" : "var(--hairline)"}`,
                    background: s.done ? "color-mix(in srgb, var(--status-good) 8%, var(--surface))" : "var(--surface)",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <Icon size={16} color={s.done ? "var(--status-good)" : "var(--ink-muted)"} />
                    {s.done ? <CheckCircle2 size={15} color="var(--status-good)" /> : <Circle size={15} color="var(--ink-muted)" />}
                  </div>
                  <span className="text-xs font-medium" style={{ color: s.done ? "var(--status-good)" : "var(--ink-primary)" }}>{s.label}</span>
                </Link>
              );
            })}
          </div>
        </Card>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-3 gap-4">
        <QuickAction to="/engagements" icon={FolderPlus} label="New engagement" sub="Start a new audit engagement" />
        <QuickAction to="/datasets/upload" icon={Upload} label="Upload dataset" sub="Ingest a population for sampling" />
        <QuickAction to="/runs/launch" icon={PlayCircle} label="Launch a run" sub="Draw a risk-based sample" />
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-3 gap-4">
        <StatTile label="Active engagements" value={engagements?.total ?? "—"} icon={Briefcase} color="blue" />
        <StatTile label="Risk runs" value={runs?.total ?? "—"} icon={FileStack} color="violet"
                  hint={Object.keys(byStatus).length ? `${byStatus.running ?? 0} running now` : undefined} />
        <StatTile label="Completed runs" value={completeCount} icon={CheckCircle2} color="good" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-3 gap-5 items-start">
        <Card>
          <CardHeader title="Runs by status" />
          <CardBody>
            {statusChartData.length === 0 ? (
              <EmptyChart icon={FileStack} text="No runs yet" />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={170}>
                  <PieChart>
                    <Pie data={statusChartData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={65} paddingAngle={statusChartData.length > 1 ? 2 : 0} startAngle={90} endAngle={-270} isAnimationActive={false}>
                      {statusChartData.map((entry) => (
                        <Cell key={entry.name} fill={STATUS_COLOR[entry.name] ?? "var(--ink-muted)"} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-2 mt-1 justify-center">
                  {statusChartData.map((s) => (
                    <span key={s.name} className="text-xs flex items-center gap-1.5" style={{ color: "var(--ink-secondary)" }}>
                      <span className="w-2 h-2 rounded-full inline-block" style={{ background: STATUS_COLOR[s.name] ?? "var(--ink-muted)" }} />
                      {s.name} ({s.value})
                    </span>
                  ))}
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Population size by dataset" />
          <CardBody>
            {datasetChartData.length === 0 ? (
              <EmptyChart icon={Database} text="No ingested datasets yet" />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={datasetChartData} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" fontSize={11} stroke="var(--ink-muted)" />
                  <YAxis type="category" dataKey="name" fontSize={11} stroke="var(--ink-muted)" width={80} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="rows" fill="var(--series-aqua)" radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Activity, last 7 days" />
          <CardBody>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={dayBuckets} margin={{ left: -20 }}>
                <XAxis dataKey="label" fontSize={11} stroke="var(--ink-muted)" />
                <YAxis fontSize={11} stroke="var(--ink-muted)" allowDecimals={false} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 12 }} />
                <defs>
                  <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--series-blue)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--series-blue)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="count" stroke="var(--series-blue)" fill="url(#activityFill)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-6 items-start">
        <Card>
          <CardHeader title="Engagements" action={<Link to="/engagements" className="text-xs font-medium flex items-center gap-1" style={{ color: "var(--accent)" }}>view all <ArrowRight size={12} /></Link>} />
          <CardBody className="p-0">
            <ul>
              {(engagements?.items ?? []).slice(0, 5).map((e) => (
                <li key={e.id} className="px-5 py-3 border-b last:border-0 flex items-center justify-between" style={{ borderColor: "var(--hairline)" }}>
                  <Link to={`/engagements/${e.id}`} className="text-sm font-medium hover:underline" style={{ color: "var(--ink-primary)" }}>{e.name}</Link>
                  <span className="text-xs capitalize" style={{ color: "var(--ink-muted)" }}>{e.status}</span>
                </li>
              ))}
              {engagements && engagements.items.length === 0 && (
                <li className="px-5 py-8 text-sm text-center" style={{ color: "var(--ink-muted)" }}>No engagements yet.</li>
              )}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Recent activity" action={<Link to="/audit-trail" className="text-xs font-medium flex items-center gap-1" style={{ color: "var(--accent)" }}>audit trail <ArrowRight size={12} /></Link>} />
          <CardBody className="p-0">
            <ul>
              {(recentEvents?.items ?? []).map((ev) => (
                <li key={ev.sequence} className="px-5 py-3 border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <div className="text-xs font-mono" style={{ color: "var(--ink-primary)" }}>{ev.action}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--ink-muted)" }}>{formatDateTime(ev.timestamp)} · {ev.actor}</div>
                </li>
              ))}
              {recentEvents && recentEvents.items.length === 0 && (
                <li className="px-5 py-8 text-sm text-center" style={{ color: "var(--ink-muted)" }}>No activity yet.</li>
              )}
            </ul>
          </CardBody>
        </Card>
      </div>

      {/* Runs needing attention */}
      <Card>
        <CardHeader title="Runs" />
        <CardBody className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left" style={{ color: "var(--ink-muted)" }}>
                <th className="px-5 py-2 font-medium">Run ID</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Progress</th>
              </tr>
            </thead>
            <tbody>
              {(runs?.items ?? []).slice(0, 6).map((r) => (
                <tr key={r.id} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                  <td className="px-5 py-2.5">
                    <Link to={`/runs/${r.run_id}/sample`} className="hover:underline font-medium" style={{ color: "var(--ink-primary)" }}>{r.run_id}</Link>
                  </td>
                  <td className="px-5 py-2.5"><StatusBadge status={r.status} /></td>
                  <td className="px-5 py-2.5 w-48">
                    <div className="w-full rounded-full h-1.5" style={{ background: "var(--hairline)" }}>
                      <div className="h-1.5 rounded-full" style={{ width: `${r.progress_pct}%`, background: r.status === "failed" ? "var(--status-critical)" : "var(--series-blue)" }} />
                    </div>
                  </td>
                </tr>
              ))}
              {runs && runs.items.length === 0 && (
                <tr><td colSpan={3} className="px-5 py-6 text-center text-sm" style={{ color: "var(--ink-muted)" }}>No risk runs yet -- launch one to get started.</td></tr>
              )}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <div className="flex items-start gap-2 text-xs px-1" style={{ color: "var(--ink-muted)" }}>
        <Info size={13} className="shrink-0 mt-0.5" />
        Benchmark verdicts aren't surfaced per-run on this page yet -- check each completed run's Benchmark tab directly.
      </div>
    </div>
  );
}

function QuickAction({ to, icon: Icon, label, sub }: { to: string; icon: typeof Upload; label: string; sub: string }) {
  return (
    <Link to={to} className="app-card app-card-hover flex items-center gap-3 px-4 py-3.5">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "#e8f1fc" }}>
        <Icon size={18} color="var(--series-blue)" />
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium" style={{ color: "var(--ink-primary)" }}>{label}</div>
        <div className="text-xs truncate" style={{ color: "var(--ink-muted)" }}>{sub}</div>
      </div>
    </Link>
  );
}

function EmptyChart({ icon: Icon, text }: { icon: typeof Database; text: string }) {
  return (
    <div className="h-[170px] flex flex-col items-center justify-center gap-2 text-sm" style={{ color: "var(--ink-muted)" }}>
      <Icon size={22} />
      {text}
    </div>
  );
}
