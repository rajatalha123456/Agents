"""End-to-end pipeline: flags -> rules -> anomaly -> risk -> sample.

Writes an audit event at each stage so the run is reconstructable from the
trail alone.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .anomaly import EnsembleConfig, detect_anomalies
from .audit_trail import AuditTrail
from .benchmark import BenchmarkResult, benchmark_ranking
from .engine import SampleResult, SamplingPolicy, build_sample
from .evaluation import ProjectionResult, project_misstatement, tested_items_from_frame
from .ingestion import add_risk_flags
from .risk import RiskWeights, aggregate_risk
from .rules import RulePack, evaluate_rules


@dataclass(frozen=True)
class RunConfig:
    tenant_id: str
    policy: SamplingPolicy
    rule_pack: RulePack | None
    risk_weights: RiskWeights
    ensemble_config: EnsembleConfig
    item_id_col: str = "item_id"
    amount_col: str = "amount"
    timestamp_col: str | None = None
    entity_col: str | None = None
    as_of: dt.date | None = None
    user_seed: str | int | None = None
    actor: str = "system"
    run_id: str = "run-0"


@dataclass
class RunResult:
    run_id: str
    frame: pd.DataFrame
    sample_result: SampleResult
    risk_scores: np.ndarray
    rules_manifest: dict
    anomaly_manifest: dict
    risk_manifest: dict
    warnings: list[str] = field(default_factory=list)

    def evidence_pack(self, projection: dict | None = None) -> dict:
        pack = self.sample_result.evidence_pack(projection)
        pack["run_id"] = self.run_id
        pack["rules_manifest"] = self.rules_manifest
        pack["anomaly_manifest"] = self.anomaly_manifest
        pack["risk_manifest"] = self.risk_manifest
        pack["warnings"] = list(self.warnings) + list(self.sample_result.warnings)
        return pack


def run_pipeline(frame: pd.DataFrame, config: RunConfig, trail: AuditTrail) -> RunResult:
    warnings: list[str] = []

    flagged = add_risk_flags(
        frame,
        amount_col=config.amount_col,
        timestamp_col=config.timestamp_col,
        entity_col=config.entity_col,
    )
    trail.append(config.actor, "pipeline.flags_added", config.run_id, {"row_count": len(flagged)})

    rules_manifest = {}
    rule_score = None
    if config.rule_pack is not None:
        as_of = config.as_of or dt.date.today()
        rule_result = evaluate_rules(flagged, config.rule_pack, as_of=as_of)
        rule_score = rule_result.scores
        rules_manifest = {
            "pack_id": config.rule_pack.pack_id,
            "pack_version": config.rule_pack.pack_version,
            "as_of": as_of.isoformat(),
            "skipped_rules": list(rule_result.skipped_rules),
            "warnings": list(rule_result.warnings),
        }
        warnings.extend(rule_result.warnings)
        trail.append(config.actor, "pipeline.rules_evaluated", config.run_id, rules_manifest)
    else:
        warnings.append("no rule pack provided; rule component absent from risk score")

    from .determinism import dataset_fingerprint
    fingerprint = dataset_fingerprint(flagged, config.item_id_col, config.amount_col)

    feature_cols = [c for c in flagged.columns if c.startswith("flag_") or c == "entity_transaction_count"]
    features = flagged[feature_cols].astype(float)
    anomaly_result = detect_anomalies(
        features, fingerprint, config=config.ensemble_config, user_seed=config.user_seed
    )
    anomaly_manifest = dict(anomaly_result.manifest)
    anomaly_manifest["warnings"] = list(anomaly_result.warnings)
    warnings.extend(anomaly_result.warnings)
    trail.append(config.actor, "pipeline.anomaly_scored", config.run_id, anomaly_manifest)

    weights = config.risk_weights
    risk_result = aggregate_risk(
        weights,
        anomaly=anomaly_result.scores,
        rules=rule_score,
    )
    risk_manifest = {
        "formula_version": weights.formula_version,
        "weights_effective": risk_result.weights_effective,
        "warnings": list(risk_result.warnings),
    }
    warnings.extend(risk_result.warnings)
    trail.append(config.actor, "pipeline.risk_aggregated", config.run_id, risk_manifest)

    flagged = flagged.copy()
    flagged["risk_score"] = risk_result.scores

    sample_result = build_sample(
        flagged, config.policy,
        item_id_col=config.item_id_col, amount_col=config.amount_col,
        risk_col="risk_score", user_seed=config.user_seed,
    )
    trail.append(config.actor, "pipeline.sample_built", config.run_id, sample_result.manifest)

    return RunResult(
        run_id=config.run_id,
        frame=flagged,
        sample_result=sample_result,
        risk_scores=risk_result.scores,
        rules_manifest=rules_manifest,
        anomaly_manifest=anomaly_manifest,
        risk_manifest=risk_manifest,
        warnings=warnings,
    )


def evaluate_run(
    run_result: RunResult,
    audit_values: dict,
    sampling_interval: float,
    confidence_level: float,
    tolerable_misstatement: float,
) -> ProjectionResult:
    items = run_result.sample_result.items.copy()
    tested_mask = items["item_id"].isin(audit_values.keys())
    untested_count = (~tested_mask).sum()

    tested_frame = items[tested_mask].copy()
    tested_frame["audit_value"] = tested_frame["item_id"].map(audit_values)

    tested = tested_items_from_frame(tested_frame)
    result = project_misstatement(
        tested, sampling_interval=sampling_interval,
        confidence_level=confidence_level, tolerable_misstatement=tolerable_misstatement,
    )
    if untested_count:
        import dataclasses
        result = dataclasses.replace(
            result,
            warnings=result.warnings + (
                f"{untested_count} sample item(s) untested and excluded from "
                "the evaluation; they are not treated as clean.",
            ),
        )
    return result


def benchmark_run(risk_scores: np.ndarray, labels: np.ndarray, **kwargs) -> BenchmarkResult:
    return benchmark_ranking(risk_scores, labels, **kwargs)
