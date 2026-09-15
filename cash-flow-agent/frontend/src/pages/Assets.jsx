import { Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { createAsset, deleteAsset, fetchAssets, updateAsset } from "../api/endpoints";
import DataTable from "../components/DataTable";
import Field from "../components/Field";
import FormCard from "../components/FormCard";
import IconButton from "../components/IconButton";
import PageHeader from "../components/PageHeader";
import Pill from "../components/Pill";
import SearchableSelect from "../components/SearchableSelect";
import { CURRENCIES } from "../constants/currencies";
import { formatAmount } from "../utils/format";

const ASSET_TYPES = [
  ["cash", "Cash"],
  ["savings", "Savings Account"],
  ["stocks", "Stocks"],
  ["bonds", "Bonds"],
  ["mutual_funds", "Mutual Funds"],
  ["etfs", "ETFs"],
  ["fixed_deposit", "Fixed Deposit"],
  ["real_estate", "Real Estate"],
  ["crypto", "Crypto"],
  ["other", "Other Investments"],
];

const ASSET_TYPE_LABEL = Object.fromEntries(ASSET_TYPES);

const LIQUIDITY_LEVELS = [
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
];

const EMPTY_FORM = {
  name: "",
  asset_type: "cash",
  current_value: "",
  currency: "USD",
  liquidity_level: "high",
  expected_return: "0",
  maturity_date: "",
};

const COLUMNS = [
  { key: "name", label: "Name", render: (a) => <span className="font-medium" style={{ color: "var(--ink-900)" }}>{a.name}</span> },
  { key: "asset_type", label: "Type", render: (a) => <span style={{ color: "var(--ink-500)" }}>{ASSET_TYPE_LABEL[a.asset_type] || a.asset_type}</span> },
  {
    key: "current_value", label: "Value", align: "right",
    render: (a) => <span className="font-medium" style={{ color: "var(--ink-900)" }}>{formatAmount(a.current_value, a.currency)}</span>,
  },
  { key: "liquidity_level", label: "Liquidity", render: (a) => <Pill tone={a.liquidity_level}>{a.liquidity_level}</Pill> },
  { key: "maturity_date", label: "Maturity", render: (a) => <span style={{ color: "var(--ink-500)" }}>{a.maturity_date || "—"}</span> },
];

export default function Assets() {
  const [assets, setAssets] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  function load() {
    fetchAssets().then(({ data }) => setAssets(data));
  }

  useEffect(load, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const payload = { ...form, maturity_date: form.maturity_date || null };
    try {
      if (editingId) {
        await updateAsset(editingId, payload);
      } else {
        await createAsset(payload);
      }
      closeForm();
      load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to save asset."));
    }
  }

  function startEdit(asset) {
    setEditingId(asset.id);
    setShowForm(true);
    setForm({
      name: asset.name,
      asset_type: asset.asset_type,
      current_value: asset.current_value,
      currency: asset.currency,
      liquidity_level: asset.liquidity_level,
      expected_return: asset.expected_return,
      maturity_date: asset.maturity_date || "",
    });
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setError("");
  }

  async function handleDelete(id) {
    await deleteAsset(id);
    load();
  }

  return (
    <div>
      <PageHeader
        title="Assets"
        subtitle="Everything you own that could contribute to your liquidity."
        action={
          !showForm && (
            <button onClick={() => setShowForm(true)} className="btn-primary">
              <Plus size={16} /> Add Asset
            </button>
          )
        }
      />

      {showForm && (
        <FormCard title={editingId ? "Edit Asset" : "New Asset"} onClose={closeForm} onSubmit={handleSubmit}>
          {error && <div className="text-sm mb-3" style={{ color: "var(--danger-600)" }}>{error}</div>}
          <div className="grid md:grid-cols-3 gap-4">
            <Field label="Name">
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </Field>
            <Field label="Type">
              <select className="input" value={form.asset_type} onChange={(e) => setForm({ ...form, asset_type: e.target.value })}>
                {ASSET_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Current Value">
              <input type="number" step="0.01" className="input" value={form.current_value} onChange={(e) => setForm({ ...form, current_value: e.target.value })} required />
            </Field>
            <Field label="Currency">
              <SearchableSelect
                options={CURRENCIES}
                value={form.currency}
                onChange={(v) => setForm({ ...form, currency: v })}
                placeholder="Select currency"
              />
            </Field>
            <Field label="Liquidity Level">
              <select className="input" value={form.liquidity_level} onChange={(e) => setForm({ ...form, liquidity_level: e.target.value })}>
                {LIQUIDITY_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Expected Return (%)">
              <input type="number" step="0.01" className="input" value={form.expected_return} onChange={(e) => setForm({ ...form, expected_return: e.target.value })} />
            </Field>
            <Field label="Maturity Date (optional)">
              <input type="date" className="input" value={form.maturity_date} onChange={(e) => setForm({ ...form, maturity_date: e.target.value })} />
            </Field>
          </div>
          <div className="flex gap-2 mt-5">
            <button type="submit" className="btn-primary">{editingId ? "Update Asset" : "Add Asset"}</button>
            <button type="button" onClick={closeForm} className="btn-secondary">Cancel</button>
          </div>
        </FormCard>
      )}

      <DataTable
        columns={COLUMNS}
        rows={assets}
        emptyMessage="No assets yet — add your first one above."
        renderActions={(a) => (
          <>
            <IconButton icon={Pencil} title="Edit" onClick={() => startEdit(a)} />
            <IconButton icon={Trash2} title="Delete" tone="danger" onClick={() => handleDelete(a.id)} />
          </>
        )}
      />
    </div>
  );
}
