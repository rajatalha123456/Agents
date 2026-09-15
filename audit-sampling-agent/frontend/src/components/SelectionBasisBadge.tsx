// Selection basis is always visible wherever a selected item appears
// (section 7.3). There is no view where a judgmental selection looks the
// same as a statistical one -- color + label + a projectable/judgmental
// tag, always together.
import type { SelectionBasis } from "../api/types";
import { PROJECTABLE_BASES } from "../api/types";

const LABELS: Record<SelectionBasis, string> = {
  mus_systematic: "MUS (systematic)",
  mus_certainty_item: "MUS (certainty)",
  random_control: "Random control",
  high_risk_mandatory: "High risk (judgmental)",
  negative_balance_100pct: "Negative balance (100%)",
  zero_balance_review: "Zero balance (review)",
  auditor_manual_inclusion: "Manual inclusion (judgmental)",
};

export function SelectionBasisBadge({ basis }: { basis: SelectionBasis | null }) {
  if (!basis) return <span className="text-slate-400 text-xs">not selected</span>;
  const projectable = PROJECTABLE_BASES.includes(basis);
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium " +
        (projectable ? "bg-blue-100 text-blue-800" : "bg-orange-100 text-orange-900")
      }
      title={projectable ? "Statistical: extrapolated to the population" : "Judgmental: not extrapolated to the population"}
    >
      {LABELS[basis]}
      <span className="opacity-70">{projectable ? "· statistical" : "· judgmental"}</span>
    </span>
  );
}
