"""
§9.1/§9.2 — confidence bands from a calibrated probability. This module
does not compute the calibrated probability itself (that's the isotonic
regression fit per universe, §9.1 — a P7 concern); it only implements the
band decision, including the one override that matters most: a sensitive
break type can never reach AUTO, no matter how high `p` is (§9.2).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from core.config import ConfidenceBandThresholds


class ConfidenceBand(str, enum.Enum):
    AUTO = "AUTO"
    SUGGEST = "SUGGEST"
    INVESTIGATE = "INVESTIGATE"
    NONE = "NONE"


@dataclass(frozen=True)
class BandInputs:
    calibrated_p: float
    is_deterministic_l1_or_l2: bool
    universe_autonomy_is_a3: bool
    break_type_is_sensitive: bool


def classify_band(inputs: BandInputs, thresholds: ConfidenceBandThresholds) -> ConfidenceBand:
    """
    §9.2 table, implemented literally:

    AUTO requires ALL of: p >= auto_min_p, deterministic L1/L2, universe on
    A3, AND break type non-sensitive. Sensitive breaks are hard-capped at
    SUGGEST regardless of p (the override in §9.2's final paragraph) — a
    break type with p=0.999 that is_sensitive still lands on SUGGEST, never
    AUTO.
    """
    if inputs.break_type_is_sensitive:
        # Sensitive breaks may still be SUGGEST/INVESTIGATE/NONE based on p,
        # they just can never cross into AUTO.
        return _band_below_auto(inputs.calibrated_p, thresholds)

    if (
        inputs.calibrated_p >= thresholds.auto_min_p
        and inputs.is_deterministic_l1_or_l2
        and inputs.universe_autonomy_is_a3
    ):
        return ConfidenceBand.AUTO

    return _band_below_auto(inputs.calibrated_p, thresholds)


def _band_below_auto(p: float, thresholds: ConfidenceBandThresholds) -> ConfidenceBand:
    if p >= thresholds.suggest_min_p:
        return ConfidenceBand.SUGGEST
    if p >= thresholds.investigate_min_p:
        return ConfidenceBand.INVESTIGATE
    return ConfidenceBand.NONE
