"""Risk score aggregation.

All components are expected on a 0-100 scale. Absent components
redistribute their weight rather than being treated as zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

UNVALIDATED_FORMULA_VERSION = "risk-formula-v1.0.0-UNVALIDATED"

_COMPONENT_NAMES = ("anomaly", "rules", "supervised", "history", "data_quality")


@dataclass(frozen=True)
class RiskWeights:
    formula_version: str = UNVALIDATED_FORMULA_VERSION
    anomaly: float = 0.25
    rules: float = 0.20
    supervised: float = 0.35
    history: float = 0.15
    data_quality: float = 0.05

    @staticmethod
    def without_labels() -> RiskWeights:
        return RiskWeights(
            formula_version=UNVALIDATED_FORMULA_VERSION,
            anomaly=0.45,
            rules=0.35,
            supervised=0.0,
            history=0.15,
            data_quality=0.05,
        )

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in _COMPONENT_NAMES}


@dataclass(frozen=True)
class RiskScoreResult:
    scores: np.ndarray
    weights_effective: dict
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _check_scale(name: str, values: np.ndarray) -> None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return
    if finite.max() <= 1.0 and finite.min() >= 0.0 and not np.allclose(finite, finite[0]):
        raise ValueError(
            f"component '{name}' looks like a 0-1 scale (max <= 1.0); risk "
            "components must be on a 0-100 scale. Multiply by 100."
        )
    if finite.min() < 0.0 or finite.max() > 100.0:
        raise ValueError(
            f"component '{name}' has values outside [0, 100]: "
            f"min={finite.min()}, max={finite.max()}"
        )


def aggregate_risk(
    weights: RiskWeights,
    anomaly: np.ndarray | None = None,
    rules: np.ndarray | None = None,
    supervised: np.ndarray | None = None,
    history: np.ndarray | None = None,
    data_quality: np.ndarray | None = None,
) -> RiskScoreResult:
    components = {
        "anomaly": anomaly,
        "rules": rules,
        "supervised": supervised,
        "history": history,
        "data_quality": data_quality,
    }

    provided = {k: v for k, v in components.items() if v is not None}
    if not provided:
        raise ValueError("at least one risk component must be provided")

    lengths = {len(np.asarray(v)) for v in provided.values()}
    if len(lengths) > 1:
        raise ValueError(f"risk components have mismatched lengths: {lengths}")
    n = lengths.pop()

    warnings: list[str] = []
    declared_weights = weights.as_dict()

    for name, values in provided.items():
        arr = np.asarray(values, dtype=float)
        _check_scale(name, arr)

    absent = [name for name in _COMPONENT_NAMES if name not in provided]
    if absent:
        warnings.append(
            f"components absent and redistributed: {', '.join(absent)}"
        )
    if "supervised" not in provided:
        warnings.append(
            "supervised component absent -- using without_labels() weighting "
            "is recommended until confirmed outcomes exist."
        )

    weight_sum = sum(declared_weights[name] for name in provided)
    if weight_sum <= 0:
        raise ValueError("sum of weights for provided components is zero")

    effective = {name: declared_weights[name] / weight_sum for name in provided}

    combined = np.zeros(n)
    for name, values in provided.items():
        combined += effective[name] * np.asarray(values, dtype=float)

    if "UNVALIDATED" in weights.formula_version:
        warnings.append(
            f"risk weights formula_version={weights.formula_version!r} is "
            "UNVALIDATED: these are initialisation defaults, not "
            "data-derived, and must not be presented as a validated risk "
            "assessment."
        )

    return RiskScoreResult(scores=combined, weights_effective=effective, warnings=tuple(warnings))
