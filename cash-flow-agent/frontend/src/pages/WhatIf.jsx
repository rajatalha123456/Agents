import { Sparkles } from "lucide-react";
import { useState } from "react";
import { runWhatIf } from "../api/endpoints";
import AlertBanner from "../components/AlertBanner";
import Field from "../components/Field";
import ForecastChart from "../components/ForecastChart";
import PageHeader from "../components/PageHeader";

const KINDS = [
  ["withdrawal", "Withdrawal"],
  ["contribution", "Contribution"],
  ["payout", "Payout"],
];

export default function WhatIf() {
  const [form, setForm] = useState({ kind: "withdrawal", amount: "", date: "", name: "What-if item" });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const { data } = await runWhatIf({ ...form, horizon: 12, scenario: "expected" });
      setResult(data);
    } catch {
      setError("Could not run the what-if scenario.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader title="What-If Analysis" subtitle="Test a hypothetical withdrawal, contribution, or payout and see the projected impact." />

      <form onSubmit={handleSubmit} className="card p-5 mb-6 grid md:grid-cols-4 gap-4 items-end">
        {error && <div className="md:col-span-4 text-sm" style={{ color: "var(--danger-600)" }}>{error}</div>}
        <Field label="Type">
          <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Amount">
          <input type="number" step="0.01" className="input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
        </Field>
        <Field label="Date">
          <input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
        </Field>
        <button type="submit" disabled={loading} className="btn-primary">
          <Sparkles size={16} /> {loading ? "Calculating..." : "Run What-If"}
        </button>
      </form>

      {result && (
        <>
          <AlertBanner alerts={result.alerts} />
          {result.explanation && (
            <div className="card p-4 mb-5 text-sm flex gap-2.5" style={{ background: "var(--brand-50)", borderColor: "var(--brand-100)" }}>
              <Sparkles size={16} className="mt-0.5 shrink-0" style={{ color: "var(--brand-600)" }} />
              <div className="whitespace-pre-wrap" style={{ color: "var(--brand-700)" }}>{result.explanation}</div>
            </div>
          )}
          <div className="grid md:grid-cols-2 gap-4">
            <ForecastChart buckets={result.baseline} title="Baseline" />
            <ForecastChart buckets={result.adjusted} title="With What-If Applied" />
          </div>
        </>
      )}
    </div>
  );
}
