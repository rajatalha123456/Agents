import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon, title, description, action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center text-center py-14 px-6">
      <div className="w-12 h-12 rounded-full flex items-center justify-center mb-3" style={{ background: "#e8f1fc" }}>
        <Icon size={22} color="var(--series-blue)" />
      </div>
      <div className="text-sm font-medium" style={{ color: "var(--ink-primary)" }}>{title}</div>
      {description && <p className="text-sm mt-1 max-w-sm" style={{ color: "var(--ink-muted)" }}>{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
