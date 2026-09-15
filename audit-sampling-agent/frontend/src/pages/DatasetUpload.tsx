import { AlertTriangle, FileUp, UploadCloud } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDataset, useEngagements, useUploadDataset } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { errorMessage, toast } from "../stores/toastStore";

export function DatasetUpload() {
  const { data: engagements } = useEngagements();
  const [engagementId, setEngagementId] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const upload = useUploadDataset();
  const { data: dataset } = useDataset(uploadedId ?? undefined, true);
  const navigate = useNavigate();

  const onFile = async (file: File) => {
    if (!engagementId) {
      toast.error("Select an engagement first.");
      return;
    }
    try {
      const result = await upload.mutateAsync({ engagementId, file });
      setUploadedId(result.id);
      toast.info(`Uploading ${file.name} — ingestion started.`);
    } catch (err) {
      toast.error(errorMessage(err, "Upload failed"));
    }
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <PageHeader title="Upload dataset" description="Drag and drop a population file to ingest for risk-based sampling." />

      <Card className="p-5 space-y-1.5">
        <label className="block text-sm font-medium" style={{ color: "var(--ink-primary)" }}>Engagement</label>
        <select value={engagementId} onChange={(e) => setEngagementId(e.target.value)} className="input w-full">
          <option value="">Select an engagement...</option>
          {(engagements?.items ?? []).map((e) => (
            <option key={e.id} value={e.id}>{e.name}</option>
          ))}
        </select>
      </Card>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) onFile(file);
        }}
        className="rounded-2xl p-12 text-center transition-colors"
        style={{
          border: `2px dashed ${dragOver ? "var(--accent)" : "var(--hairline)"}`,
          background: dragOver ? "color-mix(in srgb, var(--accent) 6%, var(--surface))" : "var(--surface)",
        }}
      >
        <div className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3" style={{ background: "#e8f1fc" }}>
          <UploadCloud size={22} color="var(--series-blue)" />
        </div>
        <p className="text-sm mb-1" style={{ color: "var(--ink-primary)" }}>Drag and drop a CSV, Parquet, or Excel file</p>
        <p className="text-xs mb-4" style={{ color: "var(--ink-muted)" }}>or click below to browse</p>
        <label className="btn btn-secondary cursor-pointer inline-flex">
          <FileUp size={14} /> Choose file
          <input
            type="file" className="hidden"
            disabled={!engagementId}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
          />
        </label>
      </div>

      {dataset && (
        <Card className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm" style={{ color: "var(--ink-primary)" }}>{dataset.filename}</span>
            <StatusBadge status={dataset.ingestion_status} />
          </div>

          {dataset.ingestion_status === "complete" && (
            <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>{dataset.row_count} rows, {dataset.column_count} columns</div>
          )}

          {dataset.ingestion_status === "failed" && (
            <div className="warning-banner flex gap-2">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <div>
                Ingestion failed. Full error, not summarized:
                <pre className="whitespace-pre-wrap mt-1 text-xs">{dataset.ingestion_error}</pre>
              </div>
            </div>
          )}

          {/* Ingestion warnings: a scrollable list, never a dismissible toast. */}
          {dataset.ingestion_warnings && dataset.ingestion_warnings.length > 0 && (
            <div>
              <div className="font-medium text-sm mb-1" style={{ color: "var(--ink-primary)" }}>Ingestion warnings ({dataset.ingestion_warnings.length})</div>
              <ul className="text-sm rounded-lg max-h-48 overflow-y-auto divide-y" style={{ border: "1px solid var(--hairline)" }}>
                {dataset.ingestion_warnings.map((w, i) => (
                  <li key={i} className="p-2" style={{ borderColor: "var(--hairline)", color: "var(--ink-secondary)" }}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {dataset.ingestion_status === "complete" && (
            <Button variant="primary" onClick={() => navigate(`/datasets/${dataset.id}/schema-mapping`)}>
              Continue to schema mapping
            </Button>
          )}
        </Card>
      )}
    </div>
  );
}
