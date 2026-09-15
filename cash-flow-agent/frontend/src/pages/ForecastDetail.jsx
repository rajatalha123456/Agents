import { useEffect, useState } from "react";
import { fetchForecast, fetchForecastCompare } from "../api/endpoints";
import AlertBanner from "../components/AlertBanner";
import DataTable from "../components/DataTable";
import ForecastChart from "../components/ForecastChart";
import LiquidityGauge from "../components/LiquidityGauge";
import PageHeader from "../components/PageHeader";
import ScenarioComparisonChart from "../components/ScenarioComparisonChart";
import TabGroup from "../components/TabGroup";
import { formatCurrency } from "../utils/format";

const HORIZONS = [
  [1, "1 Month"], [3, "3 Months"], [6, "6 Months"],
  [12, "1 Year"], [36, "3 Years"], [60, "5 Years"],
];

const SCENARIOS = [
  ["expected", "Expected Case"],
  ["best", "Best Case"],
  ["worst", "Worst Case"],
];

const COLUMNS = [
  { key: "label", label: "Month", render: (b) => <span className="font-medium" style={{ color: "var(--ink-900)" }}>{b.label}</span> },
  { key: "opening_cash", label: "Opening", align: "right", render: (b) => <span style={{ color: "var(--ink-500)" }}>{formatCurrency(b.opening_cash)}</span> },
  { key: "contributions", label: "Contributions", align: "right", render: (b) => <span style={{ color: "var(--success-600)" }}>{formatCurrency(b.contributions)}</span> },
  { key: "payouts", label: "Payouts", align: "right", render: (b) => <span style={{ color: "var(--success-600)" }}>{formatCurrency(b.payouts)}</span> },
  { key: "asset_maturities", label: "Maturities", align: "right", render: (b) => <span style={{ color: "var(--success-600)" }}>{formatCurrency(b.asset_maturities)}</span> },
  { key: "withdrawals", label: "Withdrawals", align: "right", render: (b) => <span style={{ color: "var(--danger-600)" }}>-{formatCurrency(b.withdrawals)}</span> },
  {
    key: "closing_cash", label: "Closing", align: "right",
    render: (b) => (
      <span className="font-semibold" style={{ color: b.closing_cash < 0 ? "var(--danger-600)" : "var(--ink-900)" }}>
        {formatCurrency(b.closing_cash)}
      </span>
    ),
  },
];

export default function ForecastDetail() {
  const [horizon, setHorizon] = useState(12);
  const [scenario, setScenario] = useState("expected");
  const [forecast, setForecast] = useState(null);
  const [compare, setCompare] = useState(null);

  useEffect(() => {
    fetchForecast(horizon, scenario).then(({ data }) => setForecast(data));
  }, [horizon, scenario]);

  useEffect(() => {
    fetchForecastCompare(horizon).then(({ data }) => setCompare(data.scenarios));
  }, [horizon]);

  return (
    <div>
      <PageHeader title="Forecast Detail" subtitle="Project your cash position across different time horizons and scenarios." />

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <TabGroup options={HORIZONS} value={horizon} onChange={setHorizon} />
        <div className="w-px h-5 hidden sm:block" style={{ background: "var(--border-strong)" }} />
        <TabGroup options={SCENARIOS} value={scenario} onChange={setScenario} />
      </div>

      {forecast && (
        <>
          <AlertBanner alerts={forecast.alerts} />
          <div className="mb-5 max-w-xs">
            <LiquidityGauge score={forecast.liquidity.score} band={forecast.liquidity.band} />
          </div>
          <div className="mb-6">
            <ForecastChart buckets={forecast.buckets} />
          </div>
        </>
      )}

      {compare && (
        <div className="mb-6">
          <ScenarioComparisonChart scenarios={compare} />
        </div>
      )}

      {forecast && <DataTable columns={COLUMNS} rows={forecast.buckets} rowKey="period_start" />}
    </div>
  );
}
