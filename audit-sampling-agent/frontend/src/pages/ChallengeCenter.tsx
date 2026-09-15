import { useState } from "react";
import { useParams } from "react-router-dom";
import { useCompare, useCreateOverride, useOverrides } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { RunSubNav } from "../components/RunSubNav";
import { SelectionBasisBadge } from "../components/SelectionBasisBadge";
import { errorMessage, toast } from "../stores/toastStore";
import { FileWarning } from "lucide-react";

const MIN_REASON_LENGTH = 10;

export function ChallengeCenter() {
  const { runId } = useParams();
  const [itemA, setItemA] = useState("");
  const [itemB, setItemB] = useState("");
  const compare = useCompare(runId, itemA || undefined, itemB || undefined);

  const [overrideItemId, setOverrideItemId] = useState("");
  const [action, setAction] = useState("accept");
  const [reason, setReason] = useState("");
  const createOverride = useCreateOverride();
  const { data: overrides } = useOverrides(runId);

  const reasonTooShort = reason.trim().length < MIN_REASON_LENGTH;

  const onOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reasonTooShort || !overrideItemId || !runId) return;
    try {
      await createOverride.mutateAsync({ runId, itemId: overrideItemId, action, reason });
      toast.success("Override recorded.");
      setReason("");
      setOverrideItemId("");
    } catch (err) {
      toast.error(errorMessage(err, "Could not record override"));
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Challenge center</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--ink-secondary)" }}>{runId}</p>
      </div>
      <RunSubNav runId={runId!} />

      <Card>
        <CardHeader title="Compare two items" />
        <CardBody>
          <div className="flex gap-2 mb-4">
            <input placeholder="Item A" value={itemA} onChange={(e) => setItemA(e.target.value)} className="input flex-1" />
            <input placeholder="Item B" value={itemB} onChange={(e) => setItemB(e.target.value)} className="input flex-1" />
          </div>
          {compare.data && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="font-medium mb-1" style={{ color: "var(--ink-primary)" }}>{compare.data.item_a.item_id}</div>
                <SelectionBasisBadge basis={compare.data.item_a.selection_basis} />
                <p className="mt-2" style={{ color: "var(--ink-secondary)" }}>{compare.data.item_a.reason}</p>
              </div>
              <div>
                <div className="font-medium mb-1" style={{ color: "var(--ink-primary)" }}>{compare.data.item_b.item_id}</div>
                <SelectionBasisBadge basis={compare.data.item_b.selection_basis} />
                <p className="mt-2" style={{ color: "var(--ink-secondary)" }}>{compare.data.item_b.reason}</p>
              </div>
              <div className="col-span-2 pt-3 border-t" style={{ borderColor: "var(--hairline)", color: "var(--ink-secondary)" }}>
                <div>Amount difference: {compare.data.amount_difference}</div>
                <div>Rules only in A: {compare.data.rules_only_in_a.join(", ") || "none"}</div>
                <div>Rules only in B: {compare.data.rules_only_in_b.join(", ") || "none"}</div>
                <div>Rules in both: {compare.data.rules_in_both.join(", ") || "none"}</div>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Record an override" />
        <form onSubmit={onOverride}>
          <CardBody className="space-y-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Item ID</label>
              <input value={overrideItemId} onChange={(e) => setOverrideItemId(e.target.value)} className="input w-full" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value)} className="input w-full">
                <option value="accept">Accept</option>
                <option value="add_to_sample">Add to sample</option>
                <option value="remove_from_sample">Remove from sample</option>
                <option value="override_severity">Override severity</option>
                <option value="request_rerun">Request rerun</option>
                <option value="escalate">Escalate</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>
                Reason (minimum {MIN_REASON_LENGTH} characters -- this reason enters the engagement file)
              </label>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} className="input w-full" rows={3} />
              {reason.length > 0 && reasonTooShort && (
                <p className="text-xs mt-1" style={{ color: "var(--status-critical)" }}>{MIN_REASON_LENGTH - reason.trim().length} more characters needed.</p>
              )}
            </div>
            <Button type="submit" variant="primary" disabled={reasonTooShort || !overrideItemId} loading={createOverride.isPending}>
              Record override
            </Button>
          </CardBody>
        </form>
      </Card>

      <Card>
        <CardHeader title="Overrides on this run" />
        <CardBody className="p-0">
          {(overrides?.items.length ?? 0) === 0 ? (
            <EmptyState icon={FileWarning} title="No overrides yet" description="Overrides raised on this run's sample will appear here." />
          ) : (
            <ul>
              {(overrides?.items ?? []).map((o) => (
                <li key={o.id} className="px-5 py-3 border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <div className="flex justify-between">
                    <span className="font-medium text-sm" style={{ color: "var(--ink-primary)" }}>{o.item_id}</span>
                    <span className="text-xs uppercase" style={{ color: "var(--ink-muted)" }}>{o.action}</span>
                  </div>
                  <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>{o.reason}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--ink-muted)" }}>{o.approved_by ? `approved by ${o.approved_by}` : "not yet approved"}</div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
