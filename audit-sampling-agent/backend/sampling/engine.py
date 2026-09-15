"""Sampling engine: orchestrates partitioning, high-risk, MUS, random control."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .determinism import dataset_fingerprint, library_versions
from .selection import (
    SelectionBasis,
    Stratum,
    partition_population,
    select_high_risk,
    select_monetary_unit,
    select_random,
)
from .statistics import mus_sample_size


@dataclass(frozen=True)
class SamplingPolicy:
    policy_version: str
    tolerable_misstatement: float
    confidence_level: float = 0.95
    expected_misstatement: float = 0.0
    min_sample_size: int = 0
    max_sample_size: int | None = None
    high_risk_threshold: float | None = None
    high_risk_top_n: int | None = None
    random_control_size: int = 0
    test_negative_balances_100pct: bool = True
    review_zero_balances: bool = False


@dataclass
class SampleResult:
    strata: dict[str, Stratum]
    manifest: dict
    warnings: list[str] = field(default_factory=list)

    @property
    def items(self) -> pd.DataFrame:
        frames = [s.items for s in self.strata.values() if len(s.items)]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @property
    def statistical_items(self) -> pd.DataFrame:
        frames = [
            s.items for s in self.strata.values() if s.projectable and len(s.items)
        ]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def summary(self) -> dict:
        return {
            "strata": {name: s.summary() for name, s in self.strata.items()},
            "manifest": self.manifest,
            "warnings": list(self.warnings),
        }

    def evidence_pack(self, projection: dict | None = None) -> dict:
        pack = self.summary()
        if projection is not None:
            pack["projection"] = projection
        return pack


def build_sample(
    frame: pd.DataFrame,
    policy: SamplingPolicy,
    item_id_col: str = "item_id",
    amount_col: str = "amount",
    risk_col: str | None = None,
    user_seed: str | int | None = None,
) -> SampleResult:
    warnings: list[str] = []
    fingerprint = dataset_fingerprint(frame, item_id_col, amount_col)

    parts = partition_population(frame, item_id_col, amount_col)
    positive, negative, zero = parts["positive"], parts["negative"], parts["zero"]

    strata: dict[str, Stratum] = {}

    # 1-2. High-risk judgmental stratum, drawn first so it is not double-counted.
    high_risk_items = positive.iloc[0:0].copy()
    if risk_col is not None and (
        policy.high_risk_threshold is not None or policy.high_risk_top_n is not None
    ):
        high_risk_items, hr_meta = select_high_risk(
            positive,
            risk_col=risk_col,
            threshold=policy.high_risk_threshold,
            top_n=policy.high_risk_top_n,
            item_id_col=item_id_col,
        )
        strata["high_risk"] = Stratum(
            name="high_risk",
            basis=SelectionBasis.HIGH_RISK,
            items=high_risk_items,
            population_size=len(positive),
            population_value=float(positive["_amount"].sum()) if len(positive) else 0.0,
            notes=[hr_meta["note"]],
        )

    # 3. MUS over the full positive population -- statistical conclusion must
    # cover the whole population, not only what the risk model left over.
    book_value = float(positive["_amount"].sum()) if len(positive) else 0.0
    mus_items = positive.iloc[0:0].copy()
    mus_meta: dict = {}
    if book_value > 0:
        try:
            size_result = mus_sample_size(
                book_value=book_value,
                tolerable_misstatement=policy.tolerable_misstatement,
                expected_misstatement=policy.expected_misstatement,
                confidence_level=policy.confidence_level,
                min_sample_size=policy.min_sample_size,
                max_sample_size=policy.max_sample_size,
            )
        except ValueError as exc:
            warnings.append(f"MUS sizing failed: {exc}")
            size_result = None

        if size_result is not None:
            if "CAPPED" in size_result.basis:
                warnings.append(
                    "Sample size was capped by max_sample_size; achieved "
                    "assurance is lower than the stated confidence level."
                )
            mus_items, mus_meta = select_monetary_unit(
                positive,
                sample_size=size_result.sample_size,
                sampling_interval=size_result.sampling_interval,
                dataset_fingerprint_hex=fingerprint,
                policy_version=policy.policy_version,
                user_seed=user_seed,
                exclude_ids=None,
                item_id_col=item_id_col,
            )
            mus_meta["size_result"] = size_result.as_workpaper()

    # 4. Where an item is in both high-risk and MUS, keep it in MUS (stays
    # projectable) and remove it from high-risk.
    if len(high_risk_items) and len(mus_items):
        overlap = set(high_risk_items[item_id_col]) & set(mus_items[item_id_col])
        if overlap:
            warnings.append(
                f"{len(overlap)} item(s) selected by both high-risk and MUS "
                "criteria; retained in the MUS (projectable) stratum only."
            )
            high_risk_items = high_risk_items[
                ~high_risk_items[item_id_col].isin(overlap)
            ].reset_index(drop=True)
            strata["high_risk"].items = high_risk_items

    if len(mus_items):
        strata["mus"] = Stratum(
            name="mus",
            basis=SelectionBasis.MUS,
            items=mus_items,
            population_size=len(positive),
            population_value=book_value,
            seed=mus_meta.get("seed"),
            notes=[],
        )

    # 5. Random control stratum from what remains.
    excluded_ids = set()
    if len(high_risk_items):
        excluded_ids |= set(high_risk_items[item_id_col])
    if len(mus_items):
        excluded_ids |= set(mus_items[item_id_col])

    random_items = positive.iloc[0:0].copy()
    random_meta: dict = {}
    if policy.random_control_size > 0 and len(positive):
        random_items, random_meta = select_random(
            positive,
            sample_size=policy.random_control_size,
            dataset_fingerprint_hex=fingerprint,
            policy_version=policy.policy_version,
            user_seed=user_seed,
            exclude_ids=excluded_ids,
            item_id_col=item_id_col,
        )
        if len(random_items):
            strata["random_control"] = Stratum(
                name="random_control",
                basis=SelectionBasis.RANDOM,
                items=random_items,
                population_size=len(positive),
                population_value=book_value,
                seed=random_meta.get("seed"),
                notes=[],
            )

    # 6. Negative and zero balance strata.
    if len(negative):
        neg_items = negative.copy()
        if policy.test_negative_balances_100pct:
            neg_items["_selection_basis"] = SelectionBasis.NEGATIVE_BALANCE.value
            strata["negative_balances"] = Stratum(
                name="negative_balances",
                basis=SelectionBasis.NEGATIVE_BALANCE,
                items=neg_items,
                population_size=len(negative),
                population_value=float(negative["_amount"].sum()),
                notes=["100% tested credit/negative balance stratum."],
            )
        else:
            warnings.append(
                f"{len(negative)} negative balance item(s) present but not "
                "covered -- test_negative_balances_100pct is disabled."
            )
    if len(zero):
        if policy.review_zero_balances:
            zero_items = zero.copy()
            zero_items["_selection_basis"] = SelectionBasis.ZERO_BALANCE.value
            strata["zero_balances"] = Stratum(
                name="zero_balances",
                basis=SelectionBasis.ZERO_BALANCE,
                items=zero_items,
                population_size=len(zero),
                population_value=0.0,
                notes=["Zero-balance items cannot be selected by MUS; reviewed separately."],
            )
        else:
            warnings.append(
                f"{len(zero)} zero balance item(s) present but not covered -- "
                "review_zero_balances is disabled. Zero balances are invisible "
                "to MUS and represent a completeness risk if left unreviewed."
            )

    manifest = {
        "dataset_fingerprint": fingerprint,
        "policy_version": policy.policy_version,
        "user_seed": user_seed,
        "item_id_col": item_id_col,
        "amount_col": amount_col,
        "risk_col": risk_col,
        "population_counts": {
            "positive": len(positive),
            "negative": len(negative),
            "zero": len(zero),
        },
        "book_value": book_value,
        "library_versions": library_versions(),
        "mus_selection_metadata": mus_meta,
        "random_control_metadata": random_meta,
    }

    return SampleResult(strata=strata, manifest=manifest, warnings=warnings)
