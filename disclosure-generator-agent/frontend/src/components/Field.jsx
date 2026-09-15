export default function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      {children}
    </label>
  );
}

const baseInputClasses =
  "rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 bg-white " +
  "transition-colors hover:border-slate-400 " +
  "focus:outline-none focus:ring-2 focus:ring-indigo-400/60 focus:border-indigo-400";

export function TextInput(props) {
  return <input type="text" className={baseInputClasses} {...props} />;
}

export function NumberInput(props) {
  return <input type="number" step="any" className={baseInputClasses} {...props} />;
}

export function DateInput(props) {
  return <input type="date" className={baseInputClasses} {...props} />;
}
