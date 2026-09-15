"""build_evidence_pack job: assemble and store the run's evidence export.

The full workpaper PDF / CSV / XLSX exports are a Phase 4 API-completeness
concern (section 6.1's EVIDENCE routes); this job assembles and stores the
JSON evidence pack those exports will be built from.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import RiskRun, SampleItem
from ..db.session import tenant_session


async def build_evidence_pack(tenant_id: uuid.UUID, run_pk: uuid.UUID, actor: str = "system") -> dict:
    async with tenant_session(tenant_id) as session:
        run = await session.get(RiskRun, run_pk)
        if run is None:
            raise ValueError(f"risk run {run_pk} not found")
        if run.status != "complete":
            raise ValueError(f"cannot build an evidence pack for a run in status '{run.status}'")

        result = await session.execute(
            select(SampleItem).where(SampleItem.tenant_id == tenant_id, SampleItem.run_id == run_pk)
        )
        items = list(result.scalars())

        pack = {
            "run_id": run.run_id,
            "dataset_fingerprint": run.dataset_fingerprint,
            "risk_manifest": run.risk_manifest,
            "anomaly_manifest": run.anomaly_manifest,
            "rules_manifest": run.rules_manifest,
            "sample_manifest": run.sample_manifest,
            "warnings": run.warnings,
            "sample_items": [
                {
                    "item_id": i.item_id, "stratum": i.stratum, "selection_basis": i.selection_basis,
                    "projectable": i.projectable, "amount": str(i.amount) if i.amount is not None else None,
                    "audit_value": str(i.audit_value) if i.audit_value is not None else None,
                }
                for i in items
            ],
        }

        trail = PgAuditTrail(tenant_id)
        await trail.append(session, actor=actor, action="evidence_pack.built", subject=str(run_pk),
                            payload={"item_count": len(items)})

    return pack
