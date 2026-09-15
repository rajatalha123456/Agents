import { ShieldCheck } from "lucide-react";

const BAND_STYLES = {
  Strong: { bg: "var(--success-50)", fg: "var(--success-600)", ring: "#a7f3d0" },
  Good: { bg: "var(--success-50)", fg: "var(--success-600)", ring: "#a7f3d0" },
  "Moderate Risk": { bg: "var(--warning-50)", fg: "var(--warning-600)", ring: "#fde68a" },
  "High Risk": { bg: "var(--danger-50)", fg: "var(--danger-600)", ring: "#fecaca" },
};

export default function LiquidityGauge({ score, band }) {
  const s = BAND_STYLES[band] || { bg: "#f1f5f9", fg: "var(--ink-500)", ring: "#e2e8f0" };
  const pct = Math.max(0, Math.min(100, score));

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--ink-400)" }}>
          Liquidity Score
        </div>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: s.bg, color: s.fg }}>
          <ShieldCheck size={16} strokeWidth={2.25} />
        </div>
      </div>
      <div className="flex items-end gap-2 mt-2">
        <div className="text-2xl font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink-900)" }}>
          {score}
        </div>
        <div className="text-sm mb-0.5" style={{ color: "var(--ink-400)" }}>/100</div>
      </div>
      <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: "#f1f5f9" }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: s.fg }} />
      </div>
      <div className="text-xs font-medium mt-2" style={{ color: s.fg }}>{band}</div>
    </div>
  );
}
