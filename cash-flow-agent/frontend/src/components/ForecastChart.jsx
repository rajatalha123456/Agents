import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCurrency } from "../utils/format";

export default function ForecastChart({ buckets, title = "Cash Balance Forecast" }) {
  const data = (buckets || []).map((b) => ({
    label: b.label,
    closing_cash: Number(b.closing_cash),
  }));

  return (
    <div className="card p-4 h-80">
      <div className="text-sm font-semibold mb-3" style={{ color: "var(--ink-900)" }}>{title}</div>
      <ResponsiveContainer width="100%" height="88%">
        <AreaChart data={data} margin={{ top: 5, right: 12, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={{ stroke: "#eef0f4" }} tickLine={false} />
          <YAxis
            tick={{ fontSize: 11, fill: "#94a3b8" }}
            tickFormatter={(v) => formatCurrency(v)}
            width={82}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(v) => formatCurrency(v)}
            contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 13, boxShadow: "0 8px 20px -4px rgb(15 23 42 / 0.1)" }}
          />
          <Area
            type="monotone"
            dataKey="closing_cash"
            stroke="#4f46e5"
            strokeWidth={2.25}
            fill="url(#forecastFill)"
            dot={{ r: 3, fill: "#4f46e5", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
