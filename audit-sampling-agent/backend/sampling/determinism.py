"""Determinism guarantees: canonical ordering, fingerprinting, seed derivation.

Reproducibility depends on four things, all implemented here:
canonical row order, amount quantisation before any cumulative sum, a
fingerprint over only the sampling-relevant projection of the data, and
per-stratum derived seeds fed into a pinned bit generator.
"""
from __future__ import annotations

import json
import sys
from hashlib import blake2b

import numpy as np
import pandas as pd
import scipy
import sklearn

AMOUNT_DECIMALS = 2


def round_amounts(amounts: pd.Series, decimals: int = AMOUNT_DECIMALS) -> pd.Series:
    return amounts.astype(float).round(decimals)


def canonical_order(frame: pd.DataFrame, item_id_col: str) -> pd.DataFrame:
    if frame[item_id_col].isna().any():
        raise ValueError(f"column '{item_id_col}' contains null item ids")

    dupes = frame[item_id_col][frame[item_id_col].duplicated(keep=False)]
    if not dupes.empty:
        examples = sorted(dupes.unique())[:5]
        raise ValueError(
            f"column '{item_id_col}' contains duplicate item ids "
            f"(examples: {examples}); duplicate ids destroy reproducibility "
            "and must be resolved before sampling"
        )

    ordered = frame.sort_values(item_id_col, kind="mergesort").reset_index(drop=True)
    return ordered


def dataset_fingerprint(frame: pd.DataFrame, item_id_col: str, amount_col: str) -> str:
    ordered = canonical_order(frame, item_id_col)
    ids = "\x1f".join(str(v) for v in ordered[item_id_col])
    amounts = ",".join(f"{float(v):.2f}" for v in ordered[amount_col])
    payload = (ids + "\x1e" + amounts).encode("utf-8")
    return blake2b(payload, digest_size=32).hexdigest()


def derive_seed(
    fingerprint_hex: str,
    policy_version: str,
    stratum: str,
    user_seed: str | int | None = None,
) -> int:
    material = json.dumps(
        {
            "dataset": fingerprint_hex,
            "policy_version": policy_version,
            "stratum": stratum,
            "user_seed": user_seed,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1


def make_rng(seed: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def library_versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit-learn": sklearn.__version__,
    }
