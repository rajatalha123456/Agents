import { NumberInput, TextInput } from "./Field.jsx";
import Button from "./Button.jsx";

export default function AllocationEditor({ allocation, onChange }) {
  const total = allocation.reduce((sum, item) => sum + (Number(item.weight_percent) || 0), 0);
  const withinTolerance = Math.abs(total - 100) <= 0.5;

  const updateRow = (index, key, value) => {
    const next = allocation.map((row, i) => (i === index ? { ...row, [key]: value } : row));
    onChange(next);
  };

  const removeRow = (index) => onChange(allocation.filter((_, i) => i !== index));

  const addRow = () => onChange([...allocation, { category: "", weight_percent: 0 }]);

  return (
    <div>
      <div className="space-y-2">
        {allocation.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <TextInput
              placeholder="Category"
              className="flex-1"
              value={row.category}
              onChange={(e) => updateRow(i, "category", e.target.value)}
            />
            <NumberInput
              placeholder="Weight %"
              className="w-28"
              value={row.weight_percent}
              onChange={(e) => updateRow(i, "weight_percent", Number(e.target.value))}
            />
            <Button variant="ghost" onClick={() => removeRow(i)} title="Remove">
              ✕
            </Button>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between mt-3">
        <Button variant="secondary" onClick={addRow}>
          + Add allocation
        </Button>
        <span
          className={
            "text-xs font-medium px-2 py-1 rounded-full " +
            (withinTolerance ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")
          }
        >
          Sum: {total.toFixed(2)}% {withinTolerance ? "✓ ~100%" : "✗ must be ~100%"}
        </span>
      </div>
    </div>
  );
}
