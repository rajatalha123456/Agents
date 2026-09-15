"""Population partitioning and item selection.

SelectionBasis.projectable is the product: risk-ranked and manually added
items are judgmental under ISA 530 and are never extrapolated to the
population. Every selected item carries its basis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from .determinism import derive_seed, make_rng, round_amounts


class SelectionBasis(str, Enum):
    MUS = "mus_systematic"
    MUS_CERTAINTY = "mus_certainty_item"
    RANDOM = "random_control"
    HIGH_RISK = "high_risk_mandatory"
    NEGATIVE_BALANCE = "negative_balance_100pct"
    ZERO_BALANCE = "zero_balance_review"
    AUDITOR_MANUAL = "auditor_manual_inclusion"

    @property
    def projectable(self) -> bool:
        return self in (
            SelectionBasis.MUS,
            SelectionBasis.MUS_CERTAINTY,
            SelectionBasis.RANDOM,
        )


_PROJECTABLE_BASES = frozenset(
    b for b in SelectionBasis if b.projectable
)

ISA_530_JUDGMENTAL_NOTE = (
    "Selected on a basis outside ISA 530 monetary unit sampling. Findings in "
    "this stratum are known misstatements and are not extrapolated to the "
    "population."
)


@dataclass
class Stratum:
    name: str
    basis: SelectionBasis
    items: pd.DataFrame
    population_size: int
    population_value: float
    seed: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def projectable(self) -> bool:
        return self.basis.projectable

    def summary(self) -> dict:
        return {
            "name": self.name,
            "basis": self.basis.value,
            "projectable": self.projectable,
            "items_count": len(self.items),
            "population_size": self.population_size,
            "population_value": round(self.population_value, 2),
            "seed": self.seed,
            "notes": list(self.notes),
        }


def partition_population(
    frame: pd.DataFrame, item_id_col: str, amount_col: str
) -> dict[str, pd.DataFrame]:
    working = frame.copy()
    working["_amount"] = round_amounts(working[amount_col])

    positive = working[working["_amount"] > 0].reset_index(drop=True)
    negative = working[working["_amount"] < 0].reset_index(drop=True)
    zero = working[working["_amount"] == 0].reset_index(drop=True)

    return {"positive": positive, "negative": negative, "zero": zero}


def select_monetary_unit(
    population: pd.DataFrame,
    sample_size: int,
    sampling_interval: float,
    dataset_fingerprint_hex: str,
    policy_version: str,
    user_seed: str | int | None = None,
    exclude_ids: set | None = None,
    item_id_col: str = "item_id",
) -> tuple[pd.DataFrame, dict]:
    if sample_size <= 0:
        raise ValueError("sample_size must be > 0")
    if sampling_interval <= 0:
        raise ValueError("sampling_interval must be > 0")

    pop = population.copy()
    if "_amount" not in pop.columns:
        pop["_amount"] = round_amounts(pop["amount"])

    if exclude_ids:
        pop = pop[~pop[item_id_col].isin(exclude_ids)].reset_index(drop=True)

    pop = pop.sort_values(item_id_col, kind="mergesort").reset_index(drop=True)

    amounts = pop["_amount"].to_numpy(dtype=float)
    total = float(amounts.sum())

    seed = derive_seed(dataset_fingerprint_hex, policy_version, "mus", user_seed)
    rng = make_rng(seed)

    cumulative = np.cumsum(amounts)
    random_start = float(rng.uniform(0.0, sampling_interval))
    targets = random_start + sampling_interval * np.arange(sample_size)
    targets = targets[targets < total]

    positions = np.searchsorted(cumulative, targets, side="left")
    positions = positions[positions < len(pop)]
    hit_counts = np.bincount(positions, minlength=len(pop))

    pop = pop.copy()
    pop["_hits"] = hit_counts
    pop["_inclusion_probability"] = np.minimum(amounts / sampling_interval, 1.0)

    selected = pop[pop["_hits"] > 0].copy()
    selected["_selection_basis"] = np.where(
        selected["_amount"].to_numpy(dtype=float) >= sampling_interval,
        SelectionBasis.MUS_CERTAINTY.value,
        SelectionBasis.MUS.value,
    )

    n_certainty = int((selected["_selection_basis"] == SelectionBasis.MUS_CERTAINTY.value).sum())
    n_systematic = len(selected) - n_certainty

    metadata = {
        "nominal_sample_size": sample_size,
        "distinct_items_selected": len(selected),
        "certainty_items": n_certainty,
        "systematic_items": n_systematic,
        "sampling_interval": sampling_interval,
        "random_start": random_start,
        "seed": seed,
        "total_hits": int(hit_counts.sum()),
    }
    return selected.reset_index(drop=True), metadata


def select_random(
    population: pd.DataFrame,
    sample_size: int,
    dataset_fingerprint_hex: str,
    policy_version: str,
    user_seed: str | int | None = None,
    exclude_ids: set | None = None,
    item_id_col: str = "item_id",
) -> tuple[pd.DataFrame, dict]:
    pop = population.copy()
    if exclude_ids:
        pop = pop[~pop[item_id_col].isin(exclude_ids)].reset_index(drop=True)
    pop = pop.sort_values(item_id_col, kind="mergesort").reset_index(drop=True)

    n = min(sample_size, len(pop))
    seed = derive_seed(dataset_fingerprint_hex, policy_version, "random_control", user_seed)
    rng = make_rng(seed)

    if n == 0:
        selected = pop.iloc[0:0].copy()
    else:
        idx = rng.choice(len(pop), size=n, replace=False)
        idx = np.sort(idx)
        selected = pop.iloc[idx].copy()

    selected["_selection_basis"] = SelectionBasis.RANDOM.value
    selected["_inclusion_probability"] = n / len(pop) if len(pop) else 0.0

    metadata = {
        "requested_sample_size": sample_size,
        "actual_sample_size": n,
        "population_size": len(pop),
        "seed": seed,
        "inclusion_probability": n / len(pop) if len(pop) else 0.0,
    }
    return selected.reset_index(drop=True), metadata


def select_high_risk(
    population: pd.DataFrame,
    risk_col: str,
    threshold: float | None = None,
    top_n: int | None = None,
    item_id_col: str = "item_id",
) -> tuple[pd.DataFrame, dict]:
    if threshold is None and top_n is None:
        raise ValueError("one of threshold or top_n must be provided")

    pop = population.sort_values(
        [risk_col, item_id_col], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)

    if threshold is not None:
        selected = pop[pop[risk_col] >= threshold].copy()
    else:
        selected = pop.head(top_n).copy()

    selected["_selection_basis"] = SelectionBasis.HIGH_RISK.value

    metadata = {
        "basis": SelectionBasis.HIGH_RISK.value,
        "projectable": False,
        "threshold": threshold,
        "top_n": top_n,
        "selected_count": len(selected),
        "note": ISA_530_JUDGMENTAL_NOTE,
    }
    return selected.reset_index(drop=True), metadata
