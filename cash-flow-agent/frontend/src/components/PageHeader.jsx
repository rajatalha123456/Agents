export default function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between mb-5 gap-4">
      <div>
        <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink-900)" }}>
          {title}
        </h1>
        {subtitle && <p className="text-sm mt-0.5" style={{ color: "var(--ink-500)" }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
