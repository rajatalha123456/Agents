import { CheckCircle2, Download, RefreshCw, ScrollText, XCircle } from "lucide-react";
import { useState } from "react";
import { useAuditEvents, useVerifyAuditTrail } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { formatDateTime } from "../lib/dates";

export function AuditTrailViewer() {
  const [subject, setSubject] = useState("");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const { data } = useAuditEvents({ subject: subject || undefined, actor: actor || undefined, action: action || undefined, limit: 100 });
  const verify = useVerifyAuditTrail();

  return (
    <div className="space-y-5">
      <PageHeader
        title="Audit trail"
        description="Every action, hash-chained and tamper-evident."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => verify.mutate()} loading={verify.isPending}>
              <RefreshCw size={14} /> Re-verify chain
            </Button>
            <a href="/api/v1/audit-events/export" target="_blank" rel="noreferrer" className="btn btn-secondary">
              <Download size={14} /> Export CSV
            </a>
          </div>
        }
      />

      {verify.data && (
        <div
          className="rounded-xl p-4 text-sm flex items-center gap-2"
          style={verify.data.valid
            ? { background: "color-mix(in srgb, var(--status-good) 12%, var(--surface))", border: "1px solid var(--status-good)", color: "var(--ink-primary)" }
            : { background: "color-mix(in srgb, var(--status-critical) 10%, var(--surface))", border: "1px solid var(--status-critical)", color: "var(--ink-primary)" }}
        >
          {verify.data.valid ? <CheckCircle2 size={16} color="var(--status-good)" /> : <XCircle size={16} color="var(--status-critical)" />}
          {verify.data.valid
            ? `Chain verifies: ${verify.data.events_checked} events checked, no gaps or tampering detected.`
            : `Chain INVALID at sequence ${verify.data.first_invalid_sequence}: ${verify.data.reason}`}
        </div>
      )}

      <div className="flex gap-2">
        <input placeholder="Filter by subject" value={subject} onChange={(e) => setSubject(e.target.value)} className="input text-sm" />
        <input placeholder="Filter by actor" value={actor} onChange={(e) => setActor(e.target.value)} className="input text-sm" />
        <input placeholder="Filter by action" value={action} onChange={(e) => setAction(e.target.value)} className="input text-sm" />
      </div>

      <Card className="overflow-x-auto">
        {(data?.items.length ?? 0) === 0 ? (
          <EmptyState icon={ScrollText} title="No events match" description="Try clearing the filters above." />
        ) : (
          <table className="w-full text-sm">
            <thead style={{ background: "color-mix(in srgb, var(--ink-primary) 4%, var(--surface))" }}>
              <tr className="text-left" style={{ color: "var(--ink-secondary)" }}>
                <th className="p-3 font-medium">Seq</th><th className="p-3 font-medium">Timestamp</th><th className="p-3 font-medium">Actor</th><th className="p-3 font-medium">Action</th><th className="p-3 font-medium">Subject</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((e) => (
                <tr key={e.sequence} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                  <td className="p-3 tabular" style={{ color: "var(--ink-secondary)" }}>{e.sequence}</td>
                  <td className="p-3" style={{ color: "var(--ink-secondary)" }}>{formatDateTime(e.timestamp)}</td>
                  <td className="p-3" style={{ color: "var(--ink-primary)" }}>{e.actor}</td>
                  <td className="p-3 font-mono text-xs" style={{ color: "var(--ink-primary)" }}>{e.action}</td>
                  <td className="p-3 truncate max-w-[200px]" style={{ color: "var(--ink-secondary)" }}>{e.subject}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
