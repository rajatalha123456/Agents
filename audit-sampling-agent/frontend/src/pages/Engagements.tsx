import { Briefcase, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateEngagement, useEngagements } from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { SkeletonRows } from "../components/ui/Skeleton";
import { errorMessage, toast } from "../stores/toastStore";

export function Engagements() {
  const { data, isLoading } = useEngagements();
  const create = useCreateEngagement();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await create.mutateAsync({ name, client_name: clientName });
      toast.success(`Engagement "${name}" created.`);
      setName("");
      setClientName("");
      setShowForm(false);
    } catch (err) {
      toast.error(errorMessage(err, "Could not create engagement"));
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Engagements"
        description="Periods, materiality, datasets, and runs for each audit engagement."
        action={<Button variant="primary" onClick={() => setShowForm((s) => !s)}><Plus size={16} /> New engagement</Button>}
      />

      {showForm && (
        <Card className="p-5">
          <form onSubmit={onSubmit} className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Name</label>
              <input required value={name} onChange={(e) => setName(e.target.value)} className="input w-full" />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--ink-secondary)" }}>Client</label>
              <input required value={clientName} onChange={(e) => setClientName(e.target.value)} className="input w-full" />
            </div>
            <Button type="submit" variant="primary" loading={create.isPending}>Create</Button>
          </form>
        </Card>
      )}

      <Card>
        <CardBody className="p-0">
          {isLoading && <div className="p-5"><SkeletonRows rows={3} height="h-10" /></div>}
          {!isLoading && (data?.items.length ?? 0) === 0 ? (
            <EmptyState icon={Briefcase} title="No engagements yet" description="Create one to get started." />
          ) : (
            <ul>
              {(data?.items ?? []).map((e) => (
                <li key={e.id} className="border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <Link to={`/engagements/${e.id}`} className="px-5 py-4 flex items-center gap-3 hover:bg-black/[0.02] transition-colors">
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "#e8f1fc" }}>
                      <Briefcase size={16} color="var(--series-blue)" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium" style={{ color: "var(--ink-primary)" }}>{e.name}</div>
                      <div className="text-xs" style={{ color: "var(--ink-muted)" }}>{e.client_name}</div>
                    </div>
                    <span className="text-xs capitalize px-2 py-1 rounded-full" style={{ background: "color-mix(in srgb, var(--ink-primary) 6%, var(--surface))", color: "var(--ink-secondary)" }}>{e.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
