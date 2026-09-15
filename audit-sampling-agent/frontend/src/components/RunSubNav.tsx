import { NavLink } from "react-router-dom";

const TABS = [
  { path: "sample", label: "Sample" },
  { path: "risk-dashboard", label: "Risk dashboard" },
  { path: "transactions", label: "Transactions" },
  { path: "testing", label: "Testing" },
  { path: "evaluation", label: "Evaluation" },
  { path: "challenge", label: "Challenge" },
  { path: "benchmark", label: "Benchmark" },
];

export function RunSubNav({ runId }: { runId: string }) {
  return (
    <nav className="flex gap-5 text-sm border-b overflow-x-auto" style={{ borderColor: "var(--hairline)" }}>
      {TABS.map((t) => (
        <NavLink
          key={t.path}
          to={`/runs/${runId}/${t.path}`}
          className="pb-2.5 whitespace-nowrap transition-colors"
          style={({ isActive }: { isActive: boolean }) =>
            isActive
              ? { borderBottom: "2px solid var(--accent)", color: "var(--ink-primary)", fontWeight: 600, marginBottom: "-1px" }
              : { color: "var(--ink-muted)" }
          }
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
