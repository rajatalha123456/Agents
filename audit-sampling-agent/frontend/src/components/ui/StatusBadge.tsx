import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";

// Status colors are reserved and always paired with an icon + label --
// never color alone (accessibility: hue is never the only signal).
const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: typeof CheckCircle2; label?: string }> = {
  complete: { color: "var(--status-good)", bg: "#e8f8e8", icon: CheckCircle2 },
  running: { color: "var(--series-blue)", bg: "#e8f1fc", icon: Loader2 },
  queued: { color: "var(--status-warning)", bg: "#fff6e0", icon: CircleDashed },
  pending: { color: "var(--status-warning)", bg: "#fff6e0", icon: CircleDashed },
  failed: { color: "var(--status-critical)", bg: "#fbe9e9", icon: XCircle },
  cancelled: { color: "var(--ink-muted)", bg: "#f1f0ed", icon: XCircle },
  untested: { color: "var(--status-warning)", bg: "#fff6e0", icon: AlertTriangle },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { color: "var(--ink-muted)", bg: "#f1f0ed", icon: CircleDashed };
  const Icon = cfg.icon;
  return (
    <span className="badge" style={{ background: cfg.bg, color: cfg.color }}>
      <Icon size={12} className={status === "running" ? "animate-spin" : ""} />
      {status}
    </span>
  );
}
