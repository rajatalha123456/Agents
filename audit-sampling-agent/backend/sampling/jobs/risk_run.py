"""execute_risk_run job: rules -> anomaly -> risk -> sample -> persist.

Idempotent (a completed run is never recomputed), progress-reporting,
and terminal-on-failure (never left "running" forever). For populations
above ANOMALY_SUBSAMPLE_THRESHOLD, the anomaly detectors -- which need
the whole feature matrix to be meaningful (IsolationForest, LOF) -- fit
and score a deterministic stratified subsample only; risk aggregation for
the remaining rows omits the anomaly component and lets risk.py's own
redistribution logic (absent components redistribute, never zero) carry
the weight, rather than inventing a substitute anomaly score. This is
never silent: subsample size and seed are recorded in anomaly_manifest.
"""
from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
import pandas as pd
import yaml

from ..anomaly import EnsembleConfig, detect_anomalies
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import RiskRun, RiskScore, RulePackRow, SampleItem, SamplingPolicyRow
from ..db.repositories import load_population
from ..db.session import tenant_session
from ..determinism import derive_seed, make_rng
from ..engine import SamplingPolicy, build_sample
from ..ingestion import add_risk_flags
from ..risk import RiskWeights, aggregate_risk
from ..rules import Rule, RulePack, evaluate_rules

ANOMALY_SUBSAMPLE_THRESHOLD = 500_000


def _parse_rule_pack_yaml(yaml_source: str) -> RulePack:
    """Same parsing as rules.load_rule_pack(), sourced from a string
    already read from the database instead of a file path. No safe-eval
    or scoring logic is reimplemented -- purely I/O plumbing.
    """
    raw = yaml.safe_load(yaml_source)
    rules = []
    for r in raw["rules"]:
        rules.append(Rule(
            rule_id=r["rule_id"], description=r["description"], expression=r["expression"],
            severity=r["severity"], owner=r.get("owner", "unknown"), explanation=r.get("explanation", ""),
            effective_from=dt.date.fromisoformat(str(r["effective_from"])),
            effective_to=dt.date.fromisoformat(str(r["effective_to"])) if r.get("effective_to") else None,
            required_columns=tuple(r.get("required_columns", [])),
        ))
    return RulePack(pack_id=raw["pack_id"], pack_version=raw["pack_version"], rules=tuple(rules))


async def _set_progress(session, run_id: uuid.UUID, pct: int) -> None:
    run = await session.get(RiskRun, run_id)
    run.progress_pct = pct


def _score_with_subsample(
    features: pd.DataFrame, fingerprint: str, policy_version: str,
    ensemble_config: EnsembleConfig, user_seed, rule_scores: np.ndarray, weights: RiskWeights,
) -> tuple[np.ndarray, dict, list[str]]:
    n = len(features)
    warnings: list[str] = []

    if n <= ANOMALY_SUBSAMPLE_THRESHOLD:
        anomaly_result = detect_anomalies(features, fingerprint, config=ensemble_config, user_seed=user_seed)
        risk_result = aggregate_risk(weights, anomaly=anomaly_result.scores, rules=rule_scores)
        manifest = dict(anomaly_result.manifest)
        manifest["subsampled"] = False
        return risk_result.scores, manifest, list(anomaly_result.warnings) + list(risk_result.warnings)

    seed = derive_seed(fingerprint, policy_version, "anomaly_subsample", user_seed)
    rng = make_rng(seed)
    subsample_idx = np.sort(rng.choice(n, size=ANOMALY_SUBSAMPLE_THRESHOLD, replace=False))
    subsample_mask = np.zeros(n, dtype=bool)
    subsample_mask[subsample_idx] = True

    anomaly_result = detect_anomalies(
        features.iloc[subsample_idx].reset_index(drop=True), fingerprint,
        config=ensemble_config, user_seed=user_seed,
    )

    scores = np.zeros(n)
    in_result = aggregate_risk(weights, anomaly=anomaly_result.scores, rules=rule_scores[subsample_mask])
    scores[subsample_mask] = in_result.scores

    out_result = aggregate_risk(weights, rules=rule_scores[~subsample_mask])
    scores[~subsample_mask] = out_result.scores

    warnings.append(
        f"population size {n} exceeds ANOMALY_SUBSAMPLE_THRESHOLD="
        f"{ANOMALY_SUBSAMPLE_THRESHOLD}; anomaly detection fit and scored on a "
        f"deterministic stratified subsample of {ANOMALY_SUBSAMPLE_THRESHOLD} rows "
        f"(seed={seed}). Risk scores for the remaining {n - ANOMALY_SUBSAMPLE_THRESHOLD} "
        "rows omit the anomaly component; risk.py's redistribution logic (absent "
        "components redistribute, never zero) carries that weight instead."
    )
    warnings.extend(anomaly_result.warnings)
    warnings.extend(in_result.warnings)

    manifest = dict(anomaly_result.manifest)
    manifest["subsampled"] = True
    manifest["subsample_size"] = ANOMALY_SUBSAMPLE_THRESHOLD
    manifest["subsample_seed"] = seed
    manifest["population_size"] = n

    return scores, manifest, warnings


async def execute_risk_run(tenant_id: uuid.UUID, run_pk: uuid.UUID, actor: str = "system") -> dict:
    async with tenant_session(tenant_id) as session:
        run = await session.get(RiskRun, run_pk)
        if run is None:
            raise ValueError(f"risk run {run_pk} not found")

        if run.status == "complete":
            return {"status": "complete", "run_id": run.run_id, "idempotent": True}

        policy_row = await session.get(SamplingPolicyRow, run.policy_id)
        rule_pack_row = await session.get(RulePackRow, run.rule_pack_id) if run.rule_pack_id else None

        run.status = "running"
        run.started_at = dt.datetime.now(dt.UTC)
        run.progress_pct = 0
        run.error_message = None
        await session.flush()

    try:
        async with tenant_session(tenant_id) as session:
            frame = await load_population(session, run.dataset_id)
            await _set_progress(session, run_pk, 10)

        flagged = add_risk_flags(frame, amount_col="amount")

        async with tenant_session(tenant_id) as session:
            await _set_progress(session, run_pk, 25)

        rules_manifest: dict = {}
        rule_scores = np.zeros(len(flagged))
        warnings: list[str] = []
        if rule_pack_row is not None:
            pack = _parse_rule_pack_yaml(rule_pack_row.yaml_source)
            rule_result = evaluate_rules(flagged, pack, as_of=run.as_of)
            rule_scores = rule_result.scores
            rules_manifest = {
                "pack_id": pack.pack_id, "pack_version": pack.pack_version,
                "skipped_rules": list(rule_result.skipped_rules),
            }
            warnings.extend(rule_result.warnings)

        async with tenant_session(tenant_id) as session:
            await _set_progress(session, run_pk, 45)

        feature_cols = [c for c in flagged.columns if c.startswith("flag_") or c == "entity_transaction_count"]
        features = flagged[feature_cols].astype(float)

        weights = RiskWeights.without_labels()
        scores, anomaly_manifest, anomaly_warnings = _score_with_subsample(
            features, run.dataset_fingerprint, policy_row.policy_version,
            EnsembleConfig(), run.user_seed, rule_scores, weights,
        )
        warnings.extend(anomaly_warnings)

        async with tenant_session(tenant_id) as session:
            await _set_progress(session, run_pk, 70)

        flagged = flagged.copy()
        flagged["risk_score"] = scores

        policy = SamplingPolicy(
            policy_version=policy_row.policy_version,
            tolerable_misstatement=float(policy_row.tolerable_misstatement),
            confidence_level=float(policy_row.confidence_level or 0.95),
            expected_misstatement=float(policy_row.expected_misstatement or 0),
            min_sample_size=policy_row.min_sample_size or 0,
            max_sample_size=policy_row.max_sample_size,
            high_risk_threshold=float(policy_row.high_risk_threshold) if policy_row.high_risk_threshold else None,
            high_risk_top_n=policy_row.high_risk_top_n,
            random_control_size=policy_row.random_control_size or 0,
            test_negative_balances_100pct=policy_row.test_negative_balances_100pct,
            review_zero_balances=policy_row.review_zero_balances,
        )
        sample_result = build_sample(flagged, policy, risk_col="risk_score", user_seed=run.user_seed)
        warnings.extend(sample_result.warnings)

        # Persist every item's risk score (not just the sample) in
        # bounded-size batches -- this is what the benchmark job and the
        # (Phase 4) transaction explorer read from, and a 1M-row population
        # must not be held as one giant pending INSERT.
        RISK_SCORE_BATCH = 20_000
        for start in range(0, len(flagged), RISK_SCORE_BATCH):
            batch = flagged.iloc[start:start + RISK_SCORE_BATCH]
            async with tenant_session(tenant_id) as session:
                for _, row in batch.iterrows():
                    session.add(RiskScore(
                        tenant_id=tenant_id, run_id=run_pk, item_id=str(row["item_id"]),
                        amount=float(row["amount"]), risk_score=float(row["risk_score"]),
                    ))
                await session.flush()
                session.expunge_all()

        async with tenant_session(tenant_id) as session:
            await _set_progress(session, run_pk, 90)

            run = await session.get(RiskRun, run_pk)
            run.risk_manifest = {"formula_version": weights.formula_version}
            run.anomaly_manifest = anomaly_manifest
            run.rules_manifest = rules_manifest
            run.sample_manifest = sample_result.manifest
            run.warnings = warnings
            run.status = "complete"
            run.progress_pct = 100
            run.completed_at = dt.datetime.now(dt.UTC)

            for stratum_name, stratum in sample_result.strata.items():
                for _, row in stratum.items.iterrows():
                    session.add(SampleItem(
                        tenant_id=tenant_id, run_id=run_pk, item_id=str(row["item_id"]),
                        stratum=stratum_name, selection_basis=row["_selection_basis"],
                        projectable=stratum.projectable, amount=float(row["_amount"]),
                        hits=int(row["_hits"]) if "_hits" in row else None,
                        inclusion_probability=float(row["_inclusion_probability"]) if "_inclusion_probability" in row else None,
                    ))

            trail = PgAuditTrail(tenant_id)
            await trail.append(session, actor=actor, action="risk_run.completed", subject=str(run.id),
                                payload={"run_id": run.run_id, "sample_size": len(sample_result.items)})

        return {"status": "complete", "run_id": run.run_id, "idempotent": False}

    except Exception as exc:
        async with tenant_session(tenant_id) as session:
            run = await session.get(RiskRun, run_pk)
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = dt.datetime.now(dt.UTC)
            trail = PgAuditTrail(tenant_id)
            await trail.append(session, actor=actor, action="risk_run.failed", subject=str(run_pk),
                                payload={"error": str(exc)})
        raise
