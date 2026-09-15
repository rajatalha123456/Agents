import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useExplanation, useNarrate } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { SelectionBasisBadge } from "../components/SelectionBasisBadge";
import { Warnings } from "../components/Warnings";

export function ItemDetail() {
  const { runId, itemId } = useParams();
  const { data: evidence } = useExplanation(runId, itemId);
  const narrate = useNarrate();
  const [narrated, setNarrated] = useState<Awaited<ReturnType<typeof narrate.mutateAsync>> | null>(null);

  const onNarrate = async () => {
    if (!runId || !itemId) return;
    const result = await narrate.mutateAsync({ runId, itemId });
    setNarrated(result);
  };

  if (!evidence) {
    return (
      <div className="space-y-4 max-w-3xl">
        <Skeleton className="h-8 w-64" />
        <Card className="p-5"><Skeleton className="h-24 w-full" /></Card>
      </div>
    );
  }

  const facts = evidence.facts as Record<string, unknown>;

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold" style={{ color: "var(--ink-primary)" }}>Item {evidence.item_id}</h1>
        <SelectionBasisBadge basis={evidence.selection_basis} />
      </div>

      <Warnings warnings={evidence.warnings} />

      {/* Layout order is deliberate: facts, rules fired, anomaly
          attribution, then the counterfactual -- the narrative (if any)
          goes last, clearly labelled as generated. */}
      <Card>
        <CardHeader title="Facts" />
        <CardBody>
          <dl className="text-sm grid grid-cols-2 gap-x-4">
            {Object.entries(facts).map(([k, v]) => (
              <div key={k} className="flex justify-between border-b py-2" style={{ borderColor: "var(--hairline)" }}>
                <dt style={{ color: "var(--ink-secondary)" }}>{k}</dt>
                <dd style={{ color: "var(--ink-primary)" }}>{v === null ? "not run" : String(v)}</dd>
              </div>
            ))}
          </dl>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Rules fired" />
        <CardBody>
          {evidence.rules_fired.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--ink-muted)" }}>No rules fired.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {evidence.rules_fired.map((r) => (
                <li key={r.rule_id} className="rounded-lg p-3" style={{ border: "1px solid var(--hairline)" }}>
                  <div className="font-medium" style={{ color: "var(--ink-primary)" }}>
                    {r.rule_id} <span className="text-xs uppercase" style={{ color: "var(--ink-muted)" }}>{r.severity}</span>
                  </div>
                  <div style={{ color: "var(--ink-secondary)" }}>{r.description}</div>
                  <div className="text-xs mt-1" style={{ color: "var(--ink-muted)" }}>{r.explanation}</div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Anomaly attribution" />
        <CardBody>
          {evidence.anomaly_attribution.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--ink-muted)" }}>No attribution available.</p>
          ) : (
            <ul className="text-sm">
              {evidence.anomaly_attribution.map((a, i) => (
                <li key={i} className="flex justify-between py-2 border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <span style={{ color: "var(--ink-primary)" }}>{a.feature}</span>
                  <span style={{ color: "var(--ink-secondary)" }}>robust z = {a.robust_z.toFixed(2)} (value: {a.value})</span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Counterfactual: what would have changed the outcome" />
        <CardBody>
          <p className="text-sm" style={{ color: "var(--ink-secondary)" }}>
            {evidence.selected
              ? "This item was selected; see the selection basis above for the mechanism (certainty, systematic draw, random control, or judgmental threshold)."
              : "This item was not selected. It is not a conclusion that the item is free of misstatement -- the statistical conclusion covers the population as a whole, not this item individually."}
            {typeof facts.book_value_for_certain_selection === "number" && (
              <> A book value at or above {facts.book_value_for_certain_selection} would have made MUS selection certain.</>
            )}
            {typeof facts.gap_to_high_risk_threshold === "number" && (
              <> A risk score {Math.abs(facts.gap_to_high_risk_threshold as number).toFixed(2)} points higher would have crossed the high-risk threshold.</>
            )}
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Narrative" />
        <CardBody>
          {!narrated && (
            <Button variant="secondary" onClick={onNarrate} loading={narrate.isPending}>
              <Sparkles size={14} /> Generate a narrative (LLM)
            </Button>
          )}
          {narrated && narrated.narrative && (
            <div className="text-sm rounded-lg p-3" style={{ background: "#efecfa", border: "1px solid #d7cff2" }}>
              <span className="text-xs uppercase font-medium" style={{ color: "var(--series-violet)" }}>generated narrative</span>
              <p className="mt-1" style={{ color: "var(--ink-primary)" }}>{narrated.narrative}</p>
            </div>
          )}
          {narrated && !narrated.narrative && (
            <div className="warning-banner">
              {narrated.fallback_message ?? "The generated narrative could not be verified and has been withheld."}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
