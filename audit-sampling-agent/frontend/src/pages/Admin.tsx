import { UserPlus } from "lucide-react";
import { useState } from "react";
import {
  useCurrentUser, useInviteUser, usePatchUser, useTenant, useTenantUsers, useUpdateLlmConfig, useUpdateTenant,
} from "../api/hooks";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { errorMessage, toast } from "../stores/toastStore";

export function Admin() {
  const { data: currentUser } = useCurrentUser();
  const { data: tenant } = useTenant();
  const { data: users } = useTenantUsers();
  const updateTenant = useUpdateTenant();
  const updateLlm = useUpdateLlmConfig();
  const inviteUser = useInviteUser();
  const patchUser = usePatchUser();

  const [tenantName, setTenantName] = useState("");
  const [residency, setResidency] = useState("");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("viewer");

  if (currentUser && currentUser.role !== "admin") {
    return <p style={{ color: "var(--ink-muted)" }}>Admin access required.</p>;
  }

  const onSaveTenant = () => updateTenant.mutate(
    { name: tenantName || tenant?.name, data_residency_region: residency || tenant?.data_residency_region },
    { onSuccess: () => toast.success("Tenant settings saved."), onError: (e) => toast.error(errorMessage(e, "Save failed")) },
  );
  const onSaveLlm = () => updateLlm.mutate(
    { llm_enabled: llmEnabled, llm_provider: llmProvider || null, llm_model: llmModel || null },
    { onSuccess: () => toast.success("LLM configuration saved."), onError: (e) => toast.error(errorMessage(e, "Save failed")) },
  );
  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await inviteUser.mutateAsync({ email: inviteEmail, role: inviteRole, temporary_password: crypto.randomUUID() });
      toast.success(`Invited ${inviteEmail}.`);
      setInviteEmail("");
    } catch (err) {
      toast.error(errorMessage(err, "Invite failed"));
    }
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <PageHeader title="Admin" description="Tenant settings, LLM configuration, and user management." />

      <Card>
        <CardHeader title="Tenant settings" />
        <CardBody className="space-y-3">
          <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>Current: {tenant?.name} ({tenant?.slug}), residency: {tenant?.data_residency_region}</div>
          <div className="flex gap-2">
            <input placeholder="New name" value={tenantName} onChange={(e) => setTenantName(e.target.value)} className="input flex-1 text-sm" />
            <input placeholder="Data residency region" value={residency} onChange={(e) => setResidency(e.target.value)} className="input flex-1 text-sm" />
            <Button variant="primary" onClick={onSaveTenant} loading={updateTenant.isPending}>Save</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="LLM configuration" />
        <CardBody className="space-y-3">
          <label className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-primary)" }}>
            <input type="checkbox" checked={llmEnabled} onChange={(e) => setLlmEnabled(e.target.checked)} />
            LLM features enabled
          </label>
          <div className="flex gap-2">
            <input placeholder="Provider" value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)} className="input flex-1 text-sm" />
            <input placeholder="Model" value={llmModel} onChange={(e) => setLlmModel(e.target.value)} className="input flex-1 text-sm" />
            <Button variant="primary" onClick={onSaveLlm} loading={updateLlm.isPending}>Save</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Users" />
        <CardBody className="space-y-3">
          <form onSubmit={onInvite} className="flex gap-2">
            <input placeholder="Email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="input flex-1 text-sm" />
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="input text-sm">
              <option value="viewer">viewer</option>
              <option value="auditor">auditor</option>
              <option value="reviewer">reviewer</option>
              <option value="admin">admin</option>
            </select>
            <Button type="submit" variant="primary" loading={inviteUser.isPending}><UserPlus size={14} /> Invite</Button>
          </form>

          <ul className="divide-y" style={{ borderColor: "var(--hairline)" }}>
            {(users?.items ?? []).map((u) => (
              <li key={u.id} className="py-3 flex justify-between items-center border-t first:border-0" style={{ borderColor: "var(--hairline)" }}>
                <div>
                  <div className="font-medium text-sm" style={{ color: "var(--ink-primary)" }}>{u.email}</div>
                  <div className="text-xs" style={{ color: u.is_active ? "var(--status-good)" : "var(--ink-muted)" }}>{u.is_active ? "active" : "inactive"}</div>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={u.role}
                    onChange={(e) => patchUser.mutate({ userId: u.id, patch: { role: e.target.value } }, {
                      onSuccess: () => toast.success(`Role updated for ${u.email}.`),
                    })}
                    className="input text-xs py-1"
                  >
                    <option value="viewer">viewer</option>
                    <option value="auditor">auditor</option>
                    <option value="reviewer">reviewer</option>
                    <option value="admin">admin</option>
                  </select>
                  <button
                    className="text-xs underline"
                    style={{ color: "var(--accent)" }}
                    onClick={() => patchUser.mutate({ userId: u.id, patch: { is_active: !u.is_active } }, {
                      onSuccess: () => toast.success(`${u.email} ${u.is_active ? "deactivated" : "activated"}.`),
                    })}
                  >
                    {u.is_active ? "deactivate" : "activate"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
