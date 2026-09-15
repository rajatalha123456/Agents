import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useStrata, useTransactions } from "../api/hooks";
import { Card } from "../components/ui/Card";
import { Money } from "../components/Money";
import { RunSubNav } from "../components/RunSubNav";
import { SelectionBasisBadge } from "../components/SelectionBasisBadge";

// True virtualization (react-window) isn't wired into this build; paging
// via limit/offset is used instead. Noted rather than silently claiming
// virtualization the page doesn't have.
export function TransactionExplorer() {
  const { runId } = useParams();
  const [sortBy, setSortBy] = useState<"risk_score" | "amount" | "item_id">("risk_score");
  const [stratum, setStratum] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data: strata } = useStrata(runId);
  const { data: transactions } = useTransactions(runId, { sort_by: sortBy, stratum: stratum || undefined, limit, offset });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Transaction explorer</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      <div className="flex gap-3 items-end">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Sort by</label>
          <select value={sortBy} onChange={(e) => { setSortBy(e.target.value as typeof sortBy); setOffset(0); }} className="input text-sm">
            <option value="risk_score">Risk score</option>
            <option value="amount">Amount</option>
            <option value="item_id">Item ID</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Filter by stratum</label>
          <select value={stratum} onChange={(e) => { setStratum(e.target.value); setOffset(0); }} className="input text-sm">
            <option value="">All</option>
            {Object.keys(strata?.strata ?? {}).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead style={{ background: "color-mix(in srgb, var(--ink-primary) 4%, var(--surface))" }}>
            <tr className="text-left" style={{ color: "var(--ink-secondary)" }}>
              <th className="p-3 font-medium">Item ID</th>
              <th className="p-3 font-medium">Amount</th>
              <th className="p-3 font-medium">Risk score</th>
              <th className="p-3 font-medium">Selected</th>
              <th className="p-3 font-medium">Selection basis</th>
            </tr>
          </thead>
          <tbody>
            {(transactions?.items ?? []).map((t) => (
              <tr key={t.item_id} className="border-t" style={{ borderColor: "var(--hairline)", background: t.selected ? "color-mix(in srgb, var(--series-blue) 4%, var(--surface))" : undefined }}>
                <td className="p-3">
                  <Link to={`/runs/${runId}/items/${t.item_id}`} className="hover:underline" style={{ color: "var(--ink-primary)" }}>{t.item_id}</Link>
                </td>
                <td className="p-3" style={{ color: "var(--ink-primary)" }}><Money value={t.amount} /></td>
                <td className="p-3 tabular" style={{ color: "var(--ink-secondary)" }}>{t.risk_score !== null ? t.risk_score.toFixed(2) : "not run"}</td>
                <td className="p-3" style={{ color: "var(--ink-secondary)" }}>{t.selected ? "yes" : "no"}</td>
                <td className="p-3"><SelectionBasisBadge basis={t.selection_basis} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center gap-3 text-sm" style={{ color: "var(--ink-secondary)" }}>
        <button disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - limit))} className="btn btn-secondary">
          <ChevronLeft size={14} /> Previous
        </button>
        <span>{offset + 1}–{offset + (transactions?.items.length ?? 0)} of {transactions?.total ?? "?"}</span>
        <button
          disabled={!transactions || offset + limit >= transactions.total}
          onClick={() => setOffset((o) => o + limit)}
          className="btn btn-secondary"
        >
          Next <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
