"""Persist and reload a completed sampling run -- the piece that lets a
run survive a server restart and reproduce identically from stored state
alone (policy + dataset + seed, all read back from the database, never
regenerated).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..engine import SampleResult
from .models import RiskRun, SampleItem


async def persist_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    dataset_id: uuid.UUID,
    policy_id: uuid.UUID,
    run_id: str,
    policy_version: str,
    user_seed: str | None,
    sample_result: SampleResult,
) -> RiskRun:
    run = RiskRun(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        dataset_id=dataset_id,
        policy_id=policy_id,
        run_id=run_id,
        status="complete",
        user_seed=str(user_seed) if user_seed is not None else None,
        dataset_fingerprint=sample_result.manifest["dataset_fingerprint"],
        sample_manifest=sample_result.manifest,
        warnings=list(sample_result.warnings),
    )
    session.add(run)
    await session.flush()

    for stratum_name, stratum in sample_result.strata.items():
        for _, row in stratum.items.iterrows():
            session.add(SampleItem(
                tenant_id=tenant_id,
                run_id=run.id,
                item_id=str(row["item_id"]),
                stratum=stratum_name,
                selection_basis=row["_selection_basis"],
                projectable=stratum.projectable,
                amount=float(row["_amount"]),
                hits=int(row["_hits"]) if "_hits" in row else None,
                inclusion_probability=float(row["_inclusion_probability"]) if "_inclusion_probability" in row else None,
            ))
    await session.flush()
    return run


async def load_run_by_run_id(session: AsyncSession, run_id: str) -> RiskRun | None:
    result = await session.execute(select(RiskRun).where(RiskRun.run_id == run_id))
    return result.scalar_one_or_none()


async def load_sample_item_ids(session: AsyncSession, run_pk: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(SampleItem.item_id).where(SampleItem.run_id == run_pk).order_by(SampleItem.item_id)
    )
    return [r[0] for r in result]
