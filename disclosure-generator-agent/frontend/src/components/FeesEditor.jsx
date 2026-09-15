import { NumberInput, TextInput } from "./Field.jsx";
import Button from "./Button.jsx";

export default function FeesEditor({ fees, onChange }) {
  const updateRow = (index, key, value) => {
    const next = fees.map((row, i) => (i === index ? { ...row, [key]: value } : row));
    onChange(next);
  };

  const removeRow = (index) => onChange(fees.filter((_, i) => i !== index));

  const addRow = () => onChange([...fees, { name: "", amount: 0, currency: "USD" }]);

  return (
    <div>
      <div className="space-y-2">
        {fees.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <TextInput
              placeholder="Fee name"
              className="flex-1"
              value={row.name}
              onChange={(e) => updateRow(i, "name", e.target.value)}
            />
            <NumberInput
              placeholder="Amount"
              className="w-28"
              value={row.amount}
              onChange={(e) => updateRow(i, "amount", Number(e.target.value))}
            />
            <TextInput
              placeholder="Currency"
              className="w-20"
              value={row.currency}
              onChange={(e) => updateRow(i, "currency", e.target.value)}
            />
            <Button variant="ghost" onClick={() => removeRow(i)} title="Remove">
              ✕
            </Button>
          </div>
        ))}
        {fees.length === 0 && <p className="text-xs text-slate-400">No fees.</p>}
      </div>

      <Button variant="secondary" className="mt-3" onClick={addRow}>
        + Add fee
      </Button>
    </div>
  );
}
