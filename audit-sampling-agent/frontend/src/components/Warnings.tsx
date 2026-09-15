// Warnings are never collapsed by default (section 7.3). The user may
// collapse them after reading; they never start hidden.
import { useState } from "react";

export function Warnings({ warnings }: { warnings: string[] | null | undefined }) {
  const [collapsed, setCollapsed] = useState(false);
  if (!warnings || warnings.length === 0) return null;

  return (
    <div className="warning-banner mb-4">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{warnings.length} warning{warnings.length > 1 ? "s" : ""}</span>
        <button className="text-xs underline" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? "show" : "hide"}
        </button>
      </div>
      {!collapsed && (
        <ul className="mt-2 list-disc pl-5 space-y-1">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
