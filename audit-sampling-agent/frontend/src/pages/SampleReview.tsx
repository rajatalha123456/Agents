import { Link, useParams } from "react-router-dom";
import { useSample } from "../api/hooks";
import { Money } from "../components/Money";
import { RunSubNav } from "../components/RunSubNav";
import { Warnings } from "../components/Warnings";
import type { SampleItemOut } from "../api/types";

const ISA_530_NOTE =
  "ISA 530: findings in a judgmental stratum are known misstatements and are never extrapolated to the population. " +
  "Only statistical strata (MUS, random control) support a population-level conclusion.";

export function SampleReview() {
  const { runId } = useParams();
  const { data } = useSample(runId);

  const byStratum = (data?.items ?? []).reduce<Record<string, SampleItemOut[]>>((acc, item) => {
    (acc[item.stratum] ??= []).push(item);
    return acc;
  }, {});

  const statisticalStrata = Object.entries(byStratum).filter(([, items]) => items[0]?.projectable);
  const judgmentalStrata = Object.entries(byStratum).filter(([, items]) => !items[0]?.projectable);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Sample review</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />
      <Warnings warnings={data?.warnings} />

      {/* This separation -- statistical vs judgmental, never blended into
          one table -- is the product's core claim (section 7.3). */}
      <div>
        <h2 className="text-base font-semibold mb-2" style={{ color: "var(--series-blue)" }}>Statistical strata (extrapolated to the population)</h2>
        {statisticalStrata.map(([stratum, items]) => (
          <StratumTable key={stratum} stratum={stratum} items={items} projectable runId={runId!} />
        ))}
        {statisticalStrata.length === 0 && <p className="text-sm" style={{ color: "var(--ink-muted)" }}>None.</p>}
      </div>

      <div>
        <h2 className="text-base font-semibold mb-1" style={{ color: "var(--series-orange)" }}>Judgmental strata (known misstatements only)</h2>
        <p className="text-xs rounded-lg p-2.5 mb-2" style={{ color: "var(--ink-secondary)", background: "color-mix(in srgb, var(--series-orange) 10%, var(--surface))", border: "1px solid color-mix(in srgb, var(--series-orange) 30%, var(--surface))" }}>{ISA_530_NOTE}</p>
        {judgmentalStrata.map(([stratum, items]) => (
          <StratumTable key={stratum} stratum={stratum} items={items} projectable={false} runId={runId!} />
        ))}
        {judgmentalStrata.length === 0 && <p className="text-sm" style={{ color: "var(--ink-muted)" }}>None.</p>}
      </div>
    </div>
  );
}

function StratumTable({ stratum, items, projectable, runId }: { stratum: string; items: SampleItemOut[]; projectable: boolean; runId: string }) {
  return (
    <div className="app-card mb-3" style={{ borderLeft: `3px solid ${projectable ? "var(--series-blue)" : "var(--series-orange)"}` }}>
      <div className="px-4 py-3 flex justify-between items-center border-b" style={{ borderColor: "var(--hairline)" }}>
        <span className="font-medium text-sm" style={{ color: "var(--ink-primary)" }}>{stratum}</span>
        <span className="badge" style={{ background: projectable ? "#e8f1fc" : "#fdece4", color: projectable ? "var(--series-blue)" : "var(--series-orange)" }}>
          {projectable ? "projectable" : "not projectable"}
        </span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left" style={{ color: "var(--ink-muted)" }}>
            <th className="p-2.5 pl-4">Item</th><th className="p-2.5">Amount</th><th className="p-2.5">Audit value</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.item_id} className="border-t" style={{ borderColor: "var(--hairline)" }}>
              <td className="p-2.5 pl-4"><Link to={`/runs/${runId}/items/${i.item_id}`} className="hover:underline" style={{ color: "var(--ink-primary)" }}>{i.item_id}</Link></td>
              <td className="p-2.5" style={{ color: "var(--ink-primary)" }}><Money value={i.amount} /></td>
              <td className="p-2.5" style={{ color: "var(--ink-primary)" }}><Money value={i.audit_value} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
