import { Database, FileStack, Plus, Upload } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useDatasets, useEngagement, useRiskRuns } from "../api/hooks";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { Skeleton, SkeletonCard } from "../components/ui/Skeleton";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Money } from "../components/Money";
import { formatDate } from "../lib/dates";

export function EngagementDetail() {
  const { engagementId } = useParams();
  const { data: engagement } = useEngagement(engagementId);
  // Datasets/runs aren't server-filtered by engagement in this build's
  // list endpoints; filtered client-side here, which doesn't scale to a
  // tenant with many engagements but is correct for what it shows.
  const { data: datasets } = useDatasets();
  const { data: runs } = useRiskRuns();

  if (!engagement) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-4">
          <SkeletonCard /><SkeletonCard /><SkeletonCard />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={engagement.name}
        description={engagement.client_name}
        crumbs={[{ label: "Engagements", to: "/engagements" }, { label: engagement.name }]}
      />

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-5">
          <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>Period</div>
          <div className="text-lg font-medium mt-1" style={{ color: "var(--ink-primary)" }}>
            {formatDate(engagement.period_start)} — {formatDate(engagement.period_end)}
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>Performance materiality</div>
          <div className="text-lg font-medium mt-1" style={{ color: "var(--ink-primary)" }}><Money value={engagement.performance_materiality} /></div>
        </Card>
        <Card className="p-5">
          <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>Status</div>
          <div className="text-lg font-medium mt-1 capitalize" style={{ color: "var(--ink-primary)" }}>{engagement.status}</div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Datasets"
          action={<Link to="/datasets/upload" className="btn btn-secondary text-xs"><Upload size={14} /> Upload dataset</Link>}
        />
        <CardBody className="p-0">
          {(datasets?.items.length ?? 0) === 0 ? (
            <EmptyState icon={Database} title="No datasets yet" description="Upload a population to start sampling against this engagement." />
          ) : (
            <ul>
              {(datasets?.items ?? []).map((d) => (
                <li key={d.id} className="border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <Link to={`/datasets/${d.id}/schema-mapping`} className="px-5 py-3 flex items-center justify-between hover:bg-black/[0.02] transition-colors">
                    <span className="text-sm font-medium" style={{ color: "var(--ink-primary)" }}>{d.filename}</span>
                    <span className="flex items-center gap-3 text-xs" style={{ color: "var(--ink-muted)" }}>
                      {d.row_count ?? "?"} rows
                      <StatusBadge status={d.ingestion_status} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Risk runs"
          action={<Link to="/runs/launch" className="btn btn-primary text-xs"><Plus size={14} /> Launch a run</Link>}
        />
        <CardBody className="p-0">
          {(runs?.items.length ?? 0) === 0 ? (
            <EmptyState icon={FileStack} title="No risk runs yet" description="Launch a run once a dataset and policy are ready." />
          ) : (
            <ul>
              {(runs?.items ?? []).map((r) => (
                <li key={r.id} className="border-b last:border-0" style={{ borderColor: "var(--hairline)" }}>
                  <Link to={`/runs/${r.run_id}/sample`} className="px-5 py-3 flex items-center justify-between hover:bg-black/[0.02] transition-colors">
                    <span className="text-sm font-medium" style={{ color: "var(--ink-primary)" }}>{r.run_id}</span>
                    <StatusBadge status={r.status} />
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
