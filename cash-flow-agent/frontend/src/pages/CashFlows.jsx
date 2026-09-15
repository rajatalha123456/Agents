import { Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  createCashFlowItem,
  deleteCashFlowItem,
  fetchCashFlowItems,
  fetchCashPosition,
  updateCashFlowItem,
  updateCashPosition,
} from "../api/endpoints";
import DataTable from "../components/DataTable";
import Field from "../components/Field";
import FormCard from "../components/FormCard";
import IconButton from "../components/IconButton";
import PageHeader from "../components/PageHeader";
import TabGroup from "../components/TabGroup";
import { formatCurrency } from "../utils/format";

const KINDS = [
  ["contribution", "Contributions"],
  ["withdrawal", "Withdrawals"],
  ["payout", "Payouts"],
];

const FREQUENCIES = [
  ["one_time", "One-time"],
  ["weekly", "Weekly"],
  ["monthly", "Monthly"],
  ["quarterly", "Quarterly"],
  ["yearly", "Yearly"],
];

const EMPTY_FORM = { name: "", amount: "", start_date: "", frequency: "monthly", end_date: "" };

const COLUMNS = [
  { key: "name", label: "Name", render: (i) => <span className="font-medium" style={{ color: "var(--ink-900)" }}>{i.name}</span> },
  {
    key: "amount", label: "Amount", align: "right",
    render: (i) => <span className="font-medium" style={{ color: "var(--ink-900)" }}>{formatCurrency(i.amount)}</span>,
  },
  { key: "start_date", label: "Start", render: (i) => <span style={{ color: "var(--ink-500)" }}>{i.start_date}</span> },
  { key: "frequency", label: "Frequency", render: (i) => <span className="capitalize" style={{ color: "var(--ink-500)" }}>{i.frequency.replace("_", " ")}</span> },
];

export default function CashFlows() {
  const [kind, setKind] = useState("contribution");
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);

  function load() {
    fetchCashFlowItems(kind).then(({ data }) => setItems(data));
  }

  useEffect(load, [kind]);

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form, kind, end_date: form.end_date || null };
    if (editingId) {
      await updateCashFlowItem(editingId, payload);
    } else {
      await createCashFlowItem(payload);
    }
    closeForm();
    load();
  }

  function startEdit(item) {
    setEditingId(item.id);
    setShowForm(true);
    setForm({
      name: item.name,
      amount: item.amount,
      start_date: item.start_date,
      frequency: item.frequency,
      end_date: item.end_date || "",
    });
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  async function handleDelete(id) {
    await deleteCashFlowItem(id);
    load();
  }

  return (
    <div>
      <PageHeader title="Cash Flows" subtitle="Your cash position, plus recurring contributions, withdrawals, and payouts." />

      <CashPositionCard />

      <div className="flex items-center justify-between mt-6 mb-4">
        <TabGroup options={KINDS} value={kind} onChange={(v) => { setKind(v); closeForm(); }} />
        {!showForm && (
          <button onClick={() => setShowForm(true)} className="btn-primary">
            <Plus size={16} /> Add
          </button>
        )}
      </div>

      {showForm && (
        <FormCard title={editingId ? "Edit Entry" : "New Entry"} onClose={closeForm} onSubmit={handleSubmit}>
          <div className="grid md:grid-cols-4 gap-4">
            <Field label="Name">
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </Field>
            <Field label="Amount">
              <input type="number" step="0.01" className="input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
            </Field>
            <Field label="Start Date">
              <input type="date" className="input" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} required />
            </Field>
            <Field label="Frequency">
              <select className="input" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
                {FREQUENCIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="End Date (optional)">
              <input type="date" className="input" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </Field>
          </div>
          <div className="flex gap-2 mt-5">
            <button type="submit" className="btn-primary">{editingId ? "Update" : "Add"}</button>
            <button type="button" onClick={closeForm} className="btn-secondary">Cancel</button>
          </div>
        </FormCard>
      )}

      <DataTable
        columns={COLUMNS}
        rows={items}
        emptyMessage="Nothing here yet."
        renderActions={(item) => (
          <>
            <IconButton icon={Pencil} title="Edit" onClick={() => startEdit(item)} />
            <IconButton icon={Trash2} title="Delete" tone="danger" onClick={() => handleDelete(item.id)} />
          </>
        )}
      />
    </div>
  );
}

function CashPositionCard() {
  const [position, setPosition] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchCashPosition().then(({ data }) => setPosition(data));
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    const { data } = await updateCashPosition(position);
    setPosition(data);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  if (!position) return null;

  return (
    <form onSubmit={handleSave} className="card p-5 grid md:grid-cols-5 gap-4 items-end">
      <Field label="Bank Balance">
        <input type="number" step="0.01" className="input" value={position.bank_balance} onChange={(e) => setPosition({ ...position, bank_balance: e.target.value })} />
      </Field>
      <Field label="Available Cash">
        <input type="number" step="0.01" className="input" value={position.available_cash} onChange={(e) => setPosition({ ...position, available_cash: e.target.value })} />
      </Field>
      <Field label="Emergency Fund">
        <input type="number" step="0.01" className="input" value={position.emergency_fund} onChange={(e) => setPosition({ ...position, emergency_fund: e.target.value })} />
      </Field>
      <Field label="Liquidity Alert Threshold">
        <input type="number" step="0.01" className="input" value={position.liquidity_threshold} onChange={(e) => setPosition({ ...position, liquidity_threshold: e.target.value })} />
      </Field>
      <button type="submit" className="btn-primary h-fit">{saved ? "Saved" : "Save"}</button>
    </form>
  );
}
