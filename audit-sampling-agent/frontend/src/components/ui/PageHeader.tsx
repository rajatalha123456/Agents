import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

export function PageHeader({
  title, description, crumbs, action,
}: {
  title: ReactNode;
  description?: ReactNode;
  crumbs?: Crumb[];
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        {crumbs && crumbs.length > 0 && (
          <div className="flex items-center gap-1 text-xs mb-1.5" style={{ color: "var(--ink-muted)" }}>
            {crumbs.map((c, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <ChevronRight size={12} />}
                {c.to ? <Link to={c.to} className="hover:underline">{c.label}</Link> : <span>{c.label}</span>}
              </span>
            ))}
          </div>
        )}
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>{title}</h1>
        {description && <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
