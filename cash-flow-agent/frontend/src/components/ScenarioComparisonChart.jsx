import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCurrency } from "../utils/format";

export default function ScenarioComparisonChart({ scenarios }) {
  if (!scenarios) return null;
  const labels = (scenarios.expected || []).map((b) => b.label);
  const data = labels.map((label, i) => ({
    label,
    best: Number(scenarios.best?.[i]?.closing_cash ?? 0),
    expected: Number(scenarios.expected?.[i]?.closing_cash ?? 0),
    worst: Number(scenarios.worst?.[i]?.closing_cash ?? 0),
  }));

  return (
    <div className="card p-4 h-80">
      <div className="text-sm font-semibold mb-3" style={{ color: "var(--ink-900)" }}>Scenario Comparison</div>
      <ResponsiveContainer width="100%" height="88%">
        <LineChart data={data} margin={{ top: 5, right: 12, left: 4, bottom: 0 }}>
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
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
          <Line type="monotone" dataKey="best" name="Best Case" stroke="#059669" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="expected" name="Expected" stroke="#4f46e5" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="worst" name="Worst Case" stroke="#dc2626" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
