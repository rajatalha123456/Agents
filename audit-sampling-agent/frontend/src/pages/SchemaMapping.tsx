import { AlertTriangle, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useConfirmColumnMapping, useDatasetProfile, useSchemaSuggest } from "../api/hooks";
import type { ColumnProfile } from "../api/types";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { SkeletonRows } from "../components/ui/Skeleton";
import { errorMessage, toast } from "../stores/toastStore";

export function SchemaMapping() {
  const { datasetId } = useParams();
  const { data: profileData, isLoading } = useDatasetProfile(datasetId);
  const suggest = useSchemaSuggest();
  const confirmMapping = useConfirmColumnMapping();
  const navigate = useNavigate();

  const [itemIdCol, setItemIdCol] = useState("");
  const [amountCol, setAmountCol] = useState("");
  const [timestampCol, setTimestampCol] = useState("");
  const [entityCol, setEntityCol] = useState("");
  const [acceptedSuggestions, setAcceptedSuggestions] = useState<Set<string>>(new Set());

  const columns = Object.entries(profileData?.schema_profile ?? {}) as [string, ColumnProfile][];
  const leakageCandidates = new Set(suggest.data?.leakage_candidates ?? []);

  const onSuggest = () => {
    if (!datasetId) return;
    suggest.mutate(datasetId, {
      onError: (err) => toast.error(errorMessage(err, "Could not get suggestions")),
    });
  };

  const onConfirm = async () => {
    if (!datasetId || !itemIdCol || !amountCol) return;
    try {
      await confirmMapping.mutateAsync({
        datasetId,
        mapping: { item_id_col: itemIdCol, amount_col: amountCol, timestamp_col: timestampCol || undefined, entity_col: entityCol || undefined },
      });
      toast.success("Column mapping confirmed.");
      navigate(`/policies/new`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not confirm mapping"));
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Schema mapping"
        description="Confirm which columns are the item id, amount, timestamp, and entity."
        action={
          <Button variant="secondary" onClick={onSuggest} loading={suggest.isPending}>
            <Sparkles size={14} /> {suggest.isPending ? "Asking the model..." : "Get LLM suggestions"}
          </Button>
        }
      />

      {isLoading ? (
        <SkeletonRows rows={5} height="h-10" />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead style={{ background: "color-mix(in srgb, var(--ink-primary) 4%, var(--surface))" }}>
              <tr className="text-left" style={{ color: "var(--ink-secondary)" }}>
                <th className="p-3 font-medium">Column</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium">Nulls</th>
                <th className="p-3 font-medium">Stats / samples</th>
                <th className="p-3 font-medium">Suggested role</th>
                <th className="p-3 font-medium">Map to</th>
              </tr>
            </thead>
            <tbody>
              {columns.map(([name, profile]) => {
                const suggestedRole = suggest.data?.column_roles?.[name];
                const isLeakage = leakageCandidates.has(name);
                return (
                  <tr key={name} className="border-t" style={{ borderColor: "var(--hairline)", background: isLeakage ? "color-mix(in srgb, var(--status-critical) 6%, var(--surface))" : undefined }}>
                    <td className="p-3 font-medium" style={{ color: "var(--ink-primary)" }}>
                      {name}
                      {isLeakage && (
                        <span className="ml-2 text-xs font-semibold inline-flex items-center gap-1" style={{ color: "var(--status-critical)" }} title="Flagged as a potential outcome-leakage column">
                          <AlertTriangle size={12} /> leakage risk
                        </span>
                      )}
                    </td>
                    <td className="p-3" style={{ color: "var(--ink-secondary)" }}>{profile.dtype}</td>
                    <td className="p-3" style={{ color: "var(--ink-secondary)" }}>{profile.null_pct.toFixed(1)}%</td>
                    <td className="p-3" style={{ color: "var(--ink-secondary)" }}>
                      {profile.mean !== undefined
                        ? `mean ${profile.mean.toFixed(2)}, min ${profile.min}, max ${profile.max}`
                        : (profile.sample_values ?? []).join(", ")}
                    </td>
                    <td className="p-3">
                      {suggestedRole ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="badge" style={{ background: "#efecfa", color: "var(--series-violet)" }}>
                            suggests: {suggestedRole}
                          </span>
                          {!acceptedSuggestions.has(name) && (
                            <button
                              className="text-xs underline"
                              style={{ color: "var(--accent)" }}
                              onClick={() => {
                                setAcceptedSuggestions((s) => new Set(s).add(name));
                                if (suggestedRole === "item_id") setItemIdCol(name);
                                if (suggestedRole === "amount") setAmountCol(name);
                                if (suggestedRole === "timestamp") setTimestampCol(name);
                                if (suggestedRole === "entity") setEntityCol(name);
                              }}
                            >
                              accept
                            </button>
                          )}
                        </span>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--ink-muted)" }}>—</span>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-3 text-xs" style={{ color: "var(--ink-secondary)" }}>
                        <label className="flex items-center gap-1"><input type="radio" name="item_id" checked={itemIdCol === name} onChange={() => setItemIdCol(name)} /> id</label>
                        <label className="flex items-center gap-1"><input type="radio" name="amount" checked={amountCol === name} onChange={() => setAmountCol(name)} /> amount</label>
                        <label className="flex items-center gap-1"><input type="radio" name="timestamp" checked={timestampCol === name} onChange={() => setTimestampCol(name)} /> time</label>
                        <label className="flex items-center gap-1"><input type="radio" name="entity" checked={entityCol === name} onChange={() => setEntityCol(name)} /> entity</label>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
        LLM suggestions are suggestions only, applied only when you click "accept" -- nothing is pre-applied.
        The mapping below is confirmed by you, not guessed by the system.
      </p>

      <Button variant="primary" disabled={!itemIdCol || !amountCol} loading={confirmMapping.isPending} onClick={onConfirm}>
        Confirm mapping and continue
      </Button>
    </div>
  );
}
