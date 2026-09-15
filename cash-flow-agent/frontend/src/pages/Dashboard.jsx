import { CalendarClock, PiggyBank, ShieldCheck, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchDashboardSummary } from "../api/endpoints";
import AlertBanner from "../components/AlertBanner";
import ForecastChart from "../components/ForecastChart";
import LiquidityGauge from "../components/LiquidityGauge";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import { formatCurrency } from "../utils/format";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDashboardSummary()
      .then(({ data }) => setSummary(data))
      .catch(() => setError("Could not load dashboard summary."));
  }, []);

  if (error) return <div style={{ color: "var(--danger-600)" }}>{error}</div>;
  if (!summary) return <PageSkeleton />;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Your current position and near-term outlook." />

      <AlertBanner alerts={summary.alerts} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="Current Cash" value={formatCurrency(summary.current_cash)} icon={Wallet} />
        <StatCard label="Total Assets" value={formatCurrency(summary.total_assets)} icon={PiggyBank} />
        <StatCard label="Total Liquid Assets" value={formatCurrency(summary.total_liquid_assets)} icon={ShieldCheck} tone="success" />
        <LiquidityGauge score={summary.liquidity_score} band={summary.liquidity_band} />
      </div>

      <div className="mb-6">
        <ForecastChart buckets={summary.six_month_forecast} title="6-Month Cash Balance Forecast" />
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <UpcomingList title="Upcoming Withdrawals" items={summary.upcoming_withdrawals} tone="danger" />
        <UpcomingList title="Upcoming Payouts" items={summary.upcoming_payouts} tone="success" />
        <UpcomingList title="Upcoming Contributions" items={summary.upcoming_contributions} tone="brand" />
      </div>

      <div className="mt-4">
        <UpcomingList
          title="Upcoming Asset Maturities"
          icon={CalendarClock}
          tone="brand"
          items={(summary.upcoming_maturities || []).map((m) => ({
            id: m.id,
            name: m.name,
            amount: m.current_value,
            start_date: m.maturity_date,
          }))}
        />
      </div>
    </div>
  );
}

const TONE_COLORS = {
  danger: "var(--danger-600)",
  success: "var(--success-600)",
  brand: "var(--brand-600)",
};

function UpcomingList({ title, items, tone = "brand" }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold mb-3" style={{ color: "var(--ink-900)" }}>{title}</div>
      {(!items || items.length === 0) ? (
        <div className="text-sm py-4 text-center" style={{ color: "var(--ink-400)" }}>Nothing upcoming.</div>
      ) : (
        <ul>
          {items.map((item, idx) => (
            <li
              key={item.id}
              className="py-2 flex justify-between items-center text-sm"
              style={{ borderTop: idx === 0 ? "none" : "1px solid var(--border)" }}
            >
              <span style={{ color: "var(--ink-700)" }}>{item.name}</span>
              <span className="font-semibold" style={{ color: TONE_COLORS[tone] }}>{formatCurrency(item.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-6 w-40 rounded mb-6" style={{ background: "#e5e7eb" }} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-xl" style={{ background: "#e5e7eb" }} />
        ))}
      </div>
      <div className="h-80 rounded-xl" style={{ background: "#e5e7eb" }} />
    </div>
  );
}
