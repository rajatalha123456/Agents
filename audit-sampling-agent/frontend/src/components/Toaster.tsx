import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useToastStore } from "../stores/toastStore";

const STYLE: Record<string, { bg: string; fg: string; icon: typeof CheckCircle2 }> = {
  success: { bg: "#e8f8e8", fg: "var(--status-good)", icon: CheckCircle2 },
  error: { bg: "#fbe9e9", fg: "var(--status-critical)", icon: AlertCircle },
  info: { bg: "#e8f1fc", fg: "var(--series-blue)", icon: Info },
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80">
      {toasts.map((t) => {
        const cfg = STYLE[t.kind];
        const Icon = cfg.icon;
        return (
          <div
            key={t.id}
            className="app-card flex items-start gap-2.5 px-4 py-3 animate-[slideIn_180ms_ease-out]"
            style={{ borderLeft: `3px solid ${cfg.fg}` }}
          >
            <Icon size={18} color={cfg.fg} className="shrink-0 mt-0.5" />
            <p className="text-sm flex-1" style={{ color: "var(--ink-primary)" }}>{t.message}</p>
            <button onClick={() => dismiss(t.id)} className="shrink-0" style={{ color: "var(--ink-muted)" }}>
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
