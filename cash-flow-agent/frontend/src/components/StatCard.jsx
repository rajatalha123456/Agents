export default function StatCard({ label, value, sub, icon: Icon, tone = "brand" }) {
  const tones = {
    brand: { bg: "var(--brand-50)", fg: "var(--brand-600)" },
    success: { bg: "var(--success-50)", fg: "var(--success-600)" },
    warning: { bg: "var(--warning-50)", fg: "var(--warning-600)" },
  };
  const t = tones[tone] || tones.brand;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--ink-400)" }}>
          {label}
        </div>
        {Icon && (
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: t.bg, color: t.fg }}>
            <Icon size={16} strokeWidth={2.25} />
          </div>
        )}
      </div>
      <div className="text-2xl font-semibold mt-2" style={{ fontFamily: "var(--font-display)", color: "var(--ink-900)" }}>
        {value}
      </div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--ink-400)" }}>{sub}</div>}
    </div>
  );
}
