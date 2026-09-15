"""Repository layer: the only place that converts between SQLAlchemy rows
and the pandas DataFrames the pipeline consumes.

ORDER BY item_id is mandatory on every query that feeds the sampling
engine -- the database does not promise a stable row order, and
reproducibility depends on canonical_order() being applied on top of it
regardless.
"""
from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..determinism import canonical_order, dataset_fingerprint
from .models import Dataset, DatasetRow


class DatasetFingerprintMismatch(RuntimeError):
    """Raised when the recomputed fingerprint disagrees with the one
    recorded at ingestion -- the data changed underneath a sample and the
    run must fail loudly rather than proceed.
    """


async def load_population(session: AsyncSession, dataset_id: uuid.UUID) -> pd.DataFrame:
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise ValueError(f"dataset {dataset_id} not found")

    rows = await session.execute(
        select(DatasetRow)
        .where(DatasetRow.dataset_id == dataset_id)
        .order_by(DatasetRow.item_id)
    )
    records = [
        {**r.payload, "item_id": r.item_id, "amount": float(r.amount)}
        for r in rows.scalars()
    ]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame

    frame = canonical_order(frame, "item_id")

    recomputed = dataset_fingerprint(frame, "item_id", "amount")
    if recomputed != dataset.dataset_fingerprint:
        raise DatasetFingerprintMismatch(
            f"dataset {dataset_id}: recomputed fingerprint {recomputed} does not "
            f"match the fingerprint recorded at ingestion {dataset.dataset_fingerprint}. "
            "The underlying data changed after ingestion; refusing to sample "
            "over data that no longer matches what was fingerprinted."
        )

    return frame


async def persist_dataset_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dataset_id: uuid.UUID,
    frame: pd.DataFrame,
    item_id_col: str = "item_id",
    amount_col: str = "amount",
) -> None:
    ordered = canonical_order(frame, item_id_col)
    for _, row in ordered.iterrows():
        payload = row.drop(labels=[item_id_col, amount_col], errors="ignore").to_dict()
        flags = {k: v for k, v in payload.items() if str(k).startswith("flag_")}
        session.add(
            DatasetRow(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                item_id=str(row[item_id_col]),
                amount=float(row[amount_col]),
                payload=payload,
                flags=flags or None,
            )
        )
    await session.flush()
