export default function TabGroup({ options, value, onChange }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={`tab-btn ${value === v ? "active" : ""}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
