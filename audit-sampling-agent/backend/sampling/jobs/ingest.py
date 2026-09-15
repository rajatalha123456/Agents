"""ingest_dataset job: parse, flag, fingerprint, persist rows.

Chunking applies to file parsing, flagging, and persistence -- never to
data removal (nothing is ever dropped) and never silently: a dataset
ingested in chunked mode gets a coarser (but honestly labelled) schema
profile than profile_schema()'s single-pass statistics, because computing
the frozen profile_schema() requires the whole frame in memory, which is
exactly what chunked mode exists to avoid.
"""
from __future__ import annotations

import hashlib
import math
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Dataset, DatasetRow
from ..db.session import tenant_session
from ..db.storage import resolve_path
from ..determinism import canonical_order, dataset_fingerprint, round_amounts
from ..ingestion import add_risk_flags, profile_schema

CHUNK_FILE_SIZE_BYTES = 50 * 1024 * 1024  # ~50MB triggers chunked mode
DEFAULT_CHUNK_ROWS = 50_000


async def _load_dataset(session, dataset_id: uuid.UUID) -> Dataset | None:
    result = await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    return result.scalar_one_or_none()


async def _persist_chunk(session, tenant_id: uuid.UUID, dataset_id: uuid.UUID, chunk: pd.DataFrame,
                          item_id_col: str, amount_col: str) -> None:
    for _, row in chunk.iterrows():
        payload = row.drop(labels=[item_id_col, amount_col], errors="ignore").to_dict()
        flags = {k: v for k, v in payload.items() if str(k).startswith("flag_")}
        session.add(DatasetRow(
            tenant_id=tenant_id, dataset_id=dataset_id,
            item_id=str(row[item_id_col]), amount=float(row[amount_col]),
            payload=payload, flags=flags or None,
        ))
    await session.flush()
    session.expunge_all()  # bound ORM identity-map memory across many chunks


class _RunningNumericStat:
    def __init__(self):
        self.count = 0
        self.null_count = 0
        self.min = math.inf
        self.max = -math.inf
        self.sum = 0.0
        self.negative_count = 0
        self.zero_count = 0

    def update(self, series: pd.Series) -> None:
        self.null_count += int(series.isna().sum())
        finite = series.dropna()
        if len(finite) == 0:
            return
        self.count += len(finite)
        self.min = min(self.min, float(finite.min()))
        self.max = max(self.max, float(finite.max()))
        self.sum += float(finite.sum())
        self.negative_count += int((finite < 0).sum())
        self.zero_count += int((finite == 0).sum())

    def as_dict(self) -> dict:
        n = self.null_count + self.count
        return {
            "dtype": "numeric",
            "null_count": self.null_count,
            "null_pct": round(self.null_count / n * 100, 2) if n else 0.0,
            "min": self.min if self.count else None,
            "max": self.max if self.count else None,
            "mean": (self.sum / self.count) if self.count else None,
            "negative_count": self.negative_count,
            "zero_count": self.zero_count,
            "note": "chunked-mode profile: distinct_count/median/p95 are not computed incrementally",
        }


async def ingest_dataset(
    tenant_id: uuid.UUID, dataset_id: uuid.UUID, actor: str = "system",
    item_id_col: str = "item_id", amount_col: str = "amount",
    timestamp_col: str | None = None, entity_col: str | None = None,
    chunk_rows: int = DEFAULT_CHUNK_ROWS, force_chunked: bool = False,
) -> dict:
    async with tenant_session(tenant_id) as session:
        dataset = await _load_dataset(session, dataset_id)
        if dataset is None:
            raise ValueError(f"dataset {dataset_id} not found")

        if dataset.ingestion_status == "complete":
            return {"status": "complete", "row_count": dataset.row_count, "idempotent": True}

        dataset.ingestion_status = "running"
        dataset.ingestion_error = None
        await session.flush()

    path = resolve_path(dataset.storage_key)
    file_size = Path(path).stat().st_size
    chunked_mode = force_chunked or file_size > CHUNK_FILE_SIZE_BYTES
    suffix = Path(path).suffix.lower()

    try:
        file_hash = _sha256_file(path)

        ids: list[str] = []
        amounts: list[float] = []
        warnings: list[str] = []
        numeric_stats: dict[str, _RunningNumericStat] = {}
        column_count = 0
        row_count = 0

        if chunked_mode and suffix in (".csv", ".tsv"):
            sep = "\t" if suffix == ".tsv" else ","
            reader = pd.read_csv(path, sep=sep, chunksize=chunk_rows)
            for raw_chunk in reader:
                flagged = add_risk_flags(raw_chunk, amount_col=amount_col,
                                          timestamp_col=timestamp_col, entity_col=entity_col)
                column_count = max(column_count, len(flagged.columns))
                ids.extend(str(v) for v in flagged[item_id_col])
                amounts.extend(round_amounts(flagged[amount_col]).tolist())
                row_count += len(flagged)

                for col in flagged.select_dtypes(include=[np.number]).columns:
                    numeric_stats.setdefault(col, _RunningNumericStat()).update(flagged[col])

                async with tenant_session(tenant_id) as session:
                    await _persist_chunk(session, tenant_id, dataset_id, flagged, item_id_col, amount_col)

            profile = {c: s.as_dict() for c, s in numeric_stats.items()}
            warnings.append(
                f"ingested in chunked mode ({row_count} rows, {chunk_rows}/chunk); "
                "schema profile is a coarser incremental approximation, not the "
                "single-pass profile_schema() output."
            )
        else:
            raw_frame = _read_whole(path, suffix)
            flagged = add_risk_flags(raw_frame, amount_col=amount_col,
                                      timestamp_col=timestamp_col, entity_col=entity_col)
            column_count = len(flagged.columns)
            row_count = len(flagged)
            ids = [str(v) for v in flagged[item_id_col]]
            amounts = round_amounts(flagged[amount_col]).tolist()
            profile = profile_schema(flagged)

            if flagged[item_id_col].duplicated().any():
                warnings.append("duplicate item ids present; rows retained, not dropped")
            if flagged[amount_col].isna().any():
                warnings.append("null amounts present; rows retained, not dropped")

            for start in range(0, row_count, chunk_rows):
                chunk = flagged.iloc[start:start + chunk_rows]
                async with tenant_session(tenant_id) as session:
                    await _persist_chunk(session, tenant_id, dataset_id, chunk, item_id_col, amount_col)

        fp_frame = pd.DataFrame({item_id_col: ids, amount_col: amounts})
        fp_frame = canonical_order(fp_frame, item_id_col)
        fingerprint = dataset_fingerprint(fp_frame, item_id_col, amount_col)

        async with tenant_session(tenant_id) as session:
            dataset = await _load_dataset(session, dataset_id)
            dataset.file_sha256 = file_hash
            dataset.dataset_fingerprint = fingerprint
            dataset.row_count = row_count
            dataset.column_count = column_count
            dataset.item_id_col = item_id_col
            dataset.amount_col = amount_col
            dataset.timestamp_col = timestamp_col
            dataset.entity_col = entity_col
            dataset.schema_profile = profile
            dataset.ingestion_warnings = warnings
            dataset.ingestion_status = "complete"
            trail = PgAuditTrail(tenant_id)
            await trail.append(session, actor=actor, action="dataset.ingested", subject=str(dataset_id),
                                payload={"row_count": row_count, "chunked_mode": chunked_mode})

        return {"status": "complete", "row_count": row_count, "chunked_mode": chunked_mode, "warnings": warnings}

    except Exception as exc:
        async with tenant_session(tenant_id) as session:
            dataset = await _load_dataset(session, dataset_id)
            dataset.ingestion_status = "failed"
            dataset.ingestion_error = str(exc)
            trail = PgAuditTrail(tenant_id)
            await trail.append(session, actor=actor, action="dataset.ingest_failed", subject=str(dataset_id),
                                payload={"error": str(exc)})
        raise


def _read_whole(path: str, suffix: str) -> pd.DataFrame:
    loaders = {
        ".csv": lambda p: pd.read_csv(p),
        ".tsv": lambda p: pd.read_csv(p, sep="\t"),
        ".json": lambda p: pd.read_json(p),
        ".jsonl": lambda p: pd.read_json(p, lines=True),
        ".parquet": lambda p: pd.read_parquet(p),
        ".xlsx": lambda p: pd.read_excel(p),
        ".xls": lambda p: pd.read_excel(p),
    }
    if suffix not in loaders:
        raise ValueError(f"unsupported file type: {suffix}")
    return loaders[suffix](path)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
