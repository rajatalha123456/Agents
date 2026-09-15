"""Unsupervised anomaly ensemble: IsolationForest + LOF + robust statistics
(+ optional temporal), combined by rank-normalised, re-weighted averaging.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from .determinism import derive_seed


@dataclass(frozen=True)
class EnsembleConfig:
    config_version: str = "anomaly-ensemble-v1.0.0"
    weight_isolation_forest: float = 0.35
    weight_local_outlier: float = 0.25
    weight_robust_statistical: float = 0.20
    weight_temporal: float = 0.20
    isolation_forest_trees: int = 300
    isolation_forest_contamination: float = 0.02
    local_outlier_neighbours: int = 20
    min_rows_for_local_outlier: int = 50
    min_rows_for_isolation_forest: int = 50


@dataclass(frozen=True)
class DetectorResult:
    name: str
    scores_0_100: np.ndarray
    weight_declared: float
    weight_effective: float
    ran: bool
    skip_reason: str | None = None


@dataclass(frozen=True)
class AnomalyResult:
    scores: np.ndarray
    detectors: tuple[DetectorResult, ...]
    attribution: list[list[dict]]
    manifest: dict
    warnings: tuple[str, ...] = field(default_factory=tuple)


def robust_z_scores(frame: pd.DataFrame) -> np.ndarray:
    numeric = frame.select_dtypes(include=[np.number])
    n = len(frame)
    if numeric.shape[1] == 0 or n == 0:
        return np.zeros(n)

    max_z = np.zeros(n)
    for col in numeric.columns:
        values = numeric[col].to_numpy(dtype=float)
        finite = np.isfinite(values)
        if finite.sum() == 0:
            continue
        median = np.median(values[finite])
        mad = np.median(np.abs(values[finite] - median))
        if not np.isfinite(mad) or mad == 0:
            continue
        z = np.zeros(n)
        z[finite] = np.abs(values[finite] - median) / (mad * 1.4826)
        max_z = np.maximum(max_z, np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0))
    return max_z


def _rank_pct(values: np.ndarray) -> np.ndarray:
    s = pd.Series(values)
    return s.rank(method="average", pct=True).to_numpy()


def _attribution(frame: pd.DataFrame, top_k: int = 3) -> list[list[dict]]:
    numeric = frame.select_dtypes(include=[np.number])
    n = len(frame)
    result: list[list[dict]] = [[] for _ in range(n)]
    if numeric.shape[1] == 0:
        return result

    per_col_z = {}
    for col in numeric.columns:
        values = numeric[col].to_numpy(dtype=float)
        finite = np.isfinite(values)
        if finite.sum() == 0:
            per_col_z[col] = np.zeros(n)
            continue
        median = np.median(values[finite])
        mad = np.median(np.abs(values[finite] - median))
        z = np.zeros(n)
        if np.isfinite(mad) and mad != 0:
            z[finite] = np.abs(values[finite] - median) / (mad * 1.4826)
        per_col_z[col] = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)

    cols = list(numeric.columns)
    for i in range(n):
        row_scores = [(c, per_col_z[c][i], numeric[c].iloc[i]) for c in cols]
        row_scores.sort(key=lambda t: abs(t[1]), reverse=True)
        for feature, z, raw in row_scores[:top_k]:
            result[i].append(
                {"feature": feature, "robust_z": float(z), "value": float(raw)}
            )
    return result


def detect_anomalies(
    features: pd.DataFrame,
    dataset_fingerprint_hex: str,
    config: EnsembleConfig | None = None,
    temporal_scores: np.ndarray | None = None,
    user_seed: str | int | None = None,
) -> AnomalyResult:
    config = config or EnsembleConfig()
    n = len(features)
    warnings: list[str] = []
    seed = derive_seed(dataset_fingerprint_hex, config.config_version, "anomaly", user_seed)
    # sklearn's random_state must fit in [0, 2**32 - 1]; derive_seed's 63-bit
    # space is reduced deterministically for this use only.
    sklearn_seed = seed % (2**32 - 1)

    declared_weights = {
        "isolation_forest": config.weight_isolation_forest,
        "local_outlier": config.weight_local_outlier,
        "robust_statistical": config.weight_robust_statistical,
        "temporal": config.weight_temporal,
    }

    detectors: list[DetectorResult] = []

    # Robust statistical -- always runs.
    rz = robust_z_scores(features)
    rz_pct = _rank_pct(rz) * 100.0
    detectors.append(
        DetectorResult(
            name="robust_statistical",
            scores_0_100=rz_pct,
            weight_declared=declared_weights["robust_statistical"],
            weight_effective=0.0,
            ran=True,
        )
    )

    numeric_features = features.select_dtypes(include=[np.number]).fillna(0.0)

    if n >= config.min_rows_for_isolation_forest and numeric_features.shape[1] > 0:
        iso = IsolationForest(
            n_estimators=config.isolation_forest_trees,
            contamination=config.isolation_forest_contamination,
            random_state=sklearn_seed,
            n_jobs=1,
        )
        iso_raw = -iso.fit(numeric_features).score_samples(numeric_features)
        iso_pct = _rank_pct(iso_raw) * 100.0
        detectors.append(
            DetectorResult(
                name="isolation_forest",
                scores_0_100=iso_pct,
                weight_declared=declared_weights["isolation_forest"],
                weight_effective=0.0,
                ran=True,
            )
        )
    else:
        reason = f"population size {n} below min_rows_for_isolation_forest={config.min_rows_for_isolation_forest}"
        warnings.append(f"isolation_forest skipped: {reason}")
        detectors.append(
            DetectorResult(
                name="isolation_forest",
                scores_0_100=np.zeros(n),
                weight_declared=declared_weights["isolation_forest"],
                weight_effective=0.0,
                ran=False,
                skip_reason=reason,
            )
        )

    if n >= config.min_rows_for_local_outlier and numeric_features.shape[1] > 0:
        lof = LocalOutlierFactor(
            n_neighbors=min(config.local_outlier_neighbours, n - 1),
            n_jobs=1,
        )
        lof.fit_predict(numeric_features)
        lof_raw = -lof.negative_outlier_factor_
        lof_pct = _rank_pct(lof_raw) * 100.0
        detectors.append(
            DetectorResult(
                name="local_outlier",
                scores_0_100=lof_pct,
                weight_declared=declared_weights["local_outlier"],
                weight_effective=0.0,
                ran=True,
            )
        )
    else:
        reason = f"population size {n} below min_rows_for_local_outlier={config.min_rows_for_local_outlier}"
        warnings.append(f"local_outlier skipped: {reason}")
        detectors.append(
            DetectorResult(
                name="local_outlier",
                scores_0_100=np.zeros(n),
                weight_declared=declared_weights["local_outlier"],
                weight_effective=0.0,
                ran=False,
                skip_reason=reason,
            )
        )

    if temporal_scores is not None:
        temporal_pct = _rank_pct(np.asarray(temporal_scores, dtype=float)) * 100.0
        detectors.append(
            DetectorResult(
                name="temporal",
                scores_0_100=temporal_pct,
                weight_declared=declared_weights["temporal"],
                weight_effective=0.0,
                ran=True,
            )
        )
    else:
        warnings.append("temporal detector not provided; weight redistributed")
        detectors.append(
            DetectorResult(
                name="temporal",
                scores_0_100=np.zeros(n),
                weight_declared=declared_weights["temporal"],
                weight_effective=0.0,
                ran=False,
                skip_reason="temporal_scores not provided",
            )
        )

    ran_detectors = [d for d in detectors if d.ran]
    weight_sum = sum(d.weight_declared for d in ran_detectors)
    if weight_sum <= 0:
        raise ValueError("no anomaly detectors ran; cannot compute a score")

    final_detectors: list[DetectorResult] = []
    combined = np.zeros(n)
    for d in detectors:
        if d.ran:
            effective = d.weight_declared / weight_sum
        else:
            effective = 0.0
        final_detectors.append(
            DetectorResult(
                name=d.name,
                scores_0_100=d.scores_0_100,
                weight_declared=d.weight_declared,
                weight_effective=effective,
                ran=d.ran,
                skip_reason=d.skip_reason,
            )
        )
        combined += effective * d.scores_0_100

    attribution = _attribution(features)

    manifest = {
        "config_version": config.config_version,
        "seed": seed,
        "weights_effective": {d.name: d.weight_effective for d in final_detectors},
        "calibration_note": (
            "Anomaly scores are relative rankings within this population, "
            "not probabilities, and are not comparable in absolute terms "
            "across populations of different composition."
        ),
    }

    return AnomalyResult(
        scores=combined,
        detectors=tuple(final_detectors),
        attribution=attribution,
        manifest=manifest,
        warnings=tuple(warnings),
    )
