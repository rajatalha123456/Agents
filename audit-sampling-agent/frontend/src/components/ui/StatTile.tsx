import type { LucideIcon } from "lucide-react";
import { Card } from "./Card";

const COLOR_MAP: Record<string, { bg: string; fg: string }> = {
  blue: { bg: "#e8f1fc", fg: "var(--series-blue)" },
  aqua: { bg: "#e6f7f1", fg: "var(--series-aqua)" },
  violet: { bg: "#efecfa", fg: "var(--series-violet)" },
  orange: { bg: "#fdece4", fg: "var(--series-orange)" },
  good: { bg: "#e8f8e8", fg: "var(--status-good)" },
  critical: { bg: "#fbe9e9", fg: "var(--status-critical)" },
};

export function StatTile({
  label, value, icon: Icon, color = "blue", hint,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  color?: keyof typeof COLOR_MAP;
  hint?: string;
}) {
  const c = COLOR_MAP[color];
  return (
    <Card hover className="p-5 flex items-start gap-4">
      <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: c.bg }}>
        <Icon size={20} color={c.fg} strokeWidth={2} />
      </div>
      <div className="min-w-0">
        <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>{label}</div>
        <div className="text-2xl font-semibold tabular" style={{ color: "var(--ink-primary)" }}>{value}</div>
        {hint && <div className="text-xs mt-0.5" style={{ color: "var(--ink-muted)" }}>{hint}</div>}
      </div>
    </Card>
  );
}
