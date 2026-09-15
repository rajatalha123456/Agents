"""File ingestion, schema profiling, and risk flagging.

Nothing is ever dropped here. Outliers, duplicates, missing values and odd
timestamps are the risk signal, not noise to be cleaned away.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .determinism import dataset_fingerprint


@dataclass(frozen=True)
class IngestionResult:
    frame: pd.DataFrame
    file_sha256: str
    dataset_fingerprint_hex: str | None
    row_count: int
    column_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


_LOADERS = {
    ".csv": lambda p: pd.read_csv(p),
    ".tsv": lambda p: pd.read_csv(p, sep="\t"),
    ".json": lambda p: pd.read_json(p),
    ".jsonl": lambda p: pd.read_json(p, lines=True),
    ".parquet": lambda p: pd.read_parquet(p),
    ".xlsx": lambda p: pd.read_excel(p),
    ".xls": lambda p: pd.read_excel(p),
}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest(path: str, item_id_col: str = "item_id", amount_col: str = "amount") -> IngestionResult:
    suffix = Path(path).suffix.lower()
    if suffix not in _LOADERS:
        raise ValueError(f"unsupported file type: {suffix}")

    frame = _LOADERS[suffix](path)
    file_hash = _sha256_file(path)

    warnings: list[str] = []

    if item_id_col in frame.columns:
        dupes = frame[item_id_col][frame[item_id_col].duplicated(keep=False)]
        if not dupes.empty:
            warnings.append(
                f"{dupes.nunique()} duplicate item id(s) found in "
                f"'{item_id_col}'; rows are retained, not dropped."
            )
    if amount_col in frame.columns:
        n_null = frame[amount_col].isna().sum()
        if n_null:
            warnings.append(
                f"{n_null} row(s) with null '{amount_col}'; rows are "
                "retained, not dropped."
            )

    fingerprint = None
    if item_id_col in frame.columns and amount_col in frame.columns:
        try:
            fingerprint = dataset_fingerprint(frame, item_id_col, amount_col)
        except ValueError as exc:
            warnings.append(f"fingerprint not computed: {exc}")

    return IngestionResult(
        frame=frame,
        file_sha256=file_hash,
        dataset_fingerprint_hex=fingerprint,
        row_count=len(frame),
        column_count=len(frame.columns),
        warnings=tuple(warnings),
    )


def profile_schema(frame: pd.DataFrame, sample_rows: int = 3) -> dict:
    profile = {}
    n = len(frame)
    for col in frame.columns:
        series = frame[col]
        null_count = int(series.isna().sum())
        entry = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": round(null_count / n * 100, 2) if n else 0.0,
            "distinct_count": int(series.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            finite = series.dropna()
            if len(finite):
                entry.update(
                    {
                        "min": float(finite.min()),
                        "max": float(finite.max()),
                        "mean": float(finite.mean()),
                        "median": float(finite.median()),
                        "p95": float(finite.quantile(0.95)),
                        "negative_count": int((finite < 0).sum()),
                        "zero_count": int((finite == 0).sum()),
                    }
                )
        else:
            samples = series.dropna().unique()[:sample_rows]
            entry["sample_values"] = [str(v) for v in samples]
        profile[col] = entry
    return profile


def add_risk_flags(
    frame: pd.DataFrame,
    amount_col: str = "amount",
    timestamp_col: str | None = None,
    entity_col: str | None = None,
) -> pd.DataFrame:
    out = frame.copy()
    n = len(out)

    amounts = pd.to_numeric(out[amount_col], errors="coerce") if amount_col in out.columns else pd.Series([np.nan] * n)

    out["flag_missing_amount"] = amounts.isna()
    out["flag_negative_amount"] = amounts < 0
    out["flag_zero_amount"] = amounts == 0
    out["flag_round_amount"] = (amounts.fillna(0) % 1000 == 0) & amounts.notna() & (amounts != 0)
    out["flag_duplicate_amount"] = amounts.duplicated(keep=False) & amounts.notna()

    finite = amounts.dropna()
    if len(finite):
        median = finite.median()
        mad = (finite - median).abs().median()
        if mad and np.isfinite(mad):
            robust_z = (amounts - median).abs() / (mad * 1.4826)
        else:
            robust_z = pd.Series(0.0, index=out.index)
    else:
        robust_z = pd.Series(0.0, index=out.index)
    out["flag_amount_robust_z"] = robust_z.fillna(0.0) > 3.5

    if timestamp_col and timestamp_col in out.columns:
        parsed = pd.to_datetime(out[timestamp_col], errors="coerce")
        out["flag_unparseable_timestamp"] = parsed.isna() & out[timestamp_col].notna()
        out["flag_night_transaction"] = parsed.dt.hour.isin([0, 1, 2, 3, 4, 5]) if parsed.notna().any() else False
        out["flag_weekend_transaction"] = parsed.dt.dayofweek.isin([5, 6]) if parsed.notna().any() else False
    else:
        out["flag_unparseable_timestamp"] = False
        out["flag_night_transaction"] = False
        out["flag_weekend_transaction"] = False

    if entity_col and entity_col in out.columns:
        counts = out[entity_col].value_counts()
        out["entity_transaction_count"] = out[entity_col].map(counts).fillna(0).astype(int)
        rare_threshold = max(1, int(counts.quantile(0.05))) if len(counts) else 1
        out["flag_rare_entity"] = out["entity_transaction_count"] <= rare_threshold
    else:
        out["entity_transaction_count"] = 0
        out["flag_rare_entity"] = False

    original_cols = list(frame.columns)
    out["flag_row_missing_rate"] = (
        frame[original_cols].isna().sum(axis=1) / max(len(original_cols), 1)
    )

    return out
