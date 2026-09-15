import { AlertTriangle, CalendarClock, TrendingDown, Wallet } from "lucide-react";

const CONFIG = {
  low_liquidity: { icon: AlertTriangle, bg: "var(--warning-50)", fg: "var(--warning-600)", label: "Low Liquidity" },
  cash_flow_gap: { icon: TrendingDown, bg: "var(--danger-50)", fg: "var(--danger-600)", label: "Cash Flow Gap" },
  large_withdrawal: { icon: Wallet, bg: "var(--warning-50)", fg: "var(--warning-600)", label: "Large Withdrawal" },
  asset_maturity: { icon: CalendarClock, bg: "var(--brand-50)", fg: "var(--brand-600)", label: "Asset Maturity" },
};

export default function AlertBanner({ alerts }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="space-y-2 mb-5">
      {alerts.map((alert, i) => {
        const c = CONFIG[alert.type] || { icon: AlertTriangle, bg: "#f1f5f9", fg: "var(--ink-500)", label: alert.type };
        const Icon = c.icon;
        return (
          <div
            key={i}
            className="rounded-lg px-3.5 py-2.5 text-sm flex items-start gap-2.5"
            style={{ background: c.bg, color: c.fg }}
          >
            <Icon size={16} className="mt-0.5 shrink-0" strokeWidth={2.25} />
            <div>
              <span className="font-semibold">{c.label}: </span>
              <span style={{ color: "var(--ink-700)" }}>{alert.message}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
