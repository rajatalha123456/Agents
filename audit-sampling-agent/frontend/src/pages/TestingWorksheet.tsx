import { Upload } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiRequest } from "../api/client";
import { useSample, useSetAuditValue, useTestingProgress } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Money } from "../components/Money";
import { RunSubNav } from "../components/RunSubNav";
import { errorMessage, toast } from "../stores/toastStore";

export function TestingWorksheet() {
  const { runId } = useParams();
  const { data: sample, refetch } = useSample(runId);
  const { data: progress } = useTestingProgress(runId);
  const setAuditValue = useSetAuditValue();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkPending, setBulkPending] = useState(false);

  const onSave = async (itemId: string) => {
    const raw = drafts[itemId];
    if (raw === undefined || raw === "") return;
    try {
      await setAuditValue.mutateAsync({ runId: runId!, itemId, auditValue: Number(raw) });
      toast.success(`Audit value saved for ${itemId}.`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not save audit value"));
    }
  };

  const onBulkUpload = async () => {
    if (!bulkFile || !runId) return;
    setBulkPending(true);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const result = await apiRequest<{ updated: number; missing_item_ids: string[] }>(
        `/api/v1/risk-runs/${runId}/audit-values/bulk`, { method: "POST", isFormData: true, body: form },
      );
      toast.success(`${result.updated} audit value(s) updated${result.missing_item_ids.length ? `, ${result.missing_item_ids.length} item id(s) not found` : ""}.`);
      refetch();
    } catch (err) {
      toast.error(errorMessage(err, "Bulk upload failed"));
    } finally {
      setBulkPending(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Testing worksheet</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      {progress && (
        <Card className="p-5">
          <div className="flex justify-between text-sm mb-2" style={{ color: "var(--ink-secondary)" }}>
            <span>{progress.tested_count} tested, <span className="font-medium" style={{ color: "var(--status-warning)" }}>{progress.untested_count} untested</span> of {progress.total_sample_items}</span>
            <span className="tabular">{progress.pct_complete}%</span>
          </div>
          <div className="w-full rounded-full h-2" style={{ background: "var(--hairline)" }}>
            <div className="h-2 rounded-full transition-all" style={{ width: `${progress.pct_complete}%`, background: "var(--series-blue)" }} />
          </div>
        </Card>
      )}

      <Card className="p-4 flex items-center gap-3">
        <input type="file" accept=".csv" onChange={(e) => setBulkFile(e.target.files?.[0] ?? null)} className="text-sm" style={{ color: "var(--ink-secondary)" }} />
        <Button variant="secondary" onClick={onBulkUpload} disabled={!bulkFile} loading={bulkPending}>
          <Upload size={14} /> Bulk upload CSV
        </Button>
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead style={{ background: "color-mix(in srgb, var(--ink-primary) 4%, var(--surface))" }}>
            <tr className="text-left" style={{ color: "var(--ink-secondary)" }}>
              <th className="p-3 font-medium">Item</th><th className="p-3 font-medium">Book value</th><th className="p-3 font-medium">Audit value</th><th className="p-3 font-medium">Status</th><th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {(sample?.items ?? []).map((item) => (
              <tr key={item.item_id} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                <td className="p-3" style={{ color: "var(--ink-primary)" }}>{item.item_id}</td>
                <td className="p-3" style={{ color: "var(--ink-primary)" }}><Money value={item.amount} /></td>
                <td className="p-3">
                  <input
                    type="number" step="0.01"
                    defaultValue={item.audit_value ?? ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [item.item_id]: e.target.value }))}
                    className="input w-32"
                  />
                </td>
                <td className="p-3">
                  {/* Untested items are shown as untested, never as clean. */}
                  {item.audit_value !== null ? (
                    <span className="badge" style={{ background: "#e8f8e8", color: "var(--status-good)" }}>tested</span>
                  ) : (
                    <span className="badge" style={{ background: "#fff6e0", color: "var(--status-warning)" }}>untested</span>
                  )}
                </td>
                <td className="p-3">
                  <button onClick={() => onSave(item.item_id)} className="text-xs underline" style={{ color: "var(--accent)" }}>save</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
