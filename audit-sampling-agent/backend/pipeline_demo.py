"""Demo: run the full pipeline and benchmark risk scores against confirmed
labels for two synthetic cases -- one where risk scores actually correlate
with the labels (signal case) and one where they do not (no-signal case).

Run: python pipeline_demo.py
"""
import numpy as np
import pandas as pd

from sampling.anomaly import EnsembleConfig
from sampling.audit_trail import AuditTrail
from sampling.benchmark import benchmark_ranking
from sampling.engine import SamplingPolicy
from sampling.pipeline import RunConfig, run_pipeline
from sampling.risk import RiskWeights
from sampling.rules import load_rule_pack


def _population(n: int, seed: int, with_signal: bool) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    ids = [f"TXN{i:06d}" for i in range(n)]
    amounts = np.round(rng.exponential(1500, n), 2)
    approver_count = rng.integers(1, 3, n)
    posting_hour = rng.integers(0, 24, n)
    vendor_is_new = rng.integers(0, 2, n)
    vendor_txn = rng.integers(0, 30, n)

    labels = np.zeros(n)
    n_findings = 60
    finding_idx = rng.choice(n, size=n_findings, replace=False)
    labels[finding_idx] = 1

    if with_signal:
        # Confirmed findings are concentrated in large, single-approver,
        # new-vendor payments -- exactly what the rule pack and risk model
        # are built to catch.
        amounts[finding_idx] = rng.uniform(40_000, 90_000, n_findings)
        approver_count[finding_idx] = 1
        vendor_is_new[finding_idx] = 1

    df = pd.DataFrame({
        "item_id": ids, "amount": amounts, "approver_count": approver_count,
        "posting_hour": posting_hour, "vendor_is_new": vendor_is_new,
        "vendor_transaction_count_30d": vendor_txn,
    })
    return df, labels


def _run(label: str, with_signal: bool) -> None:
    df, labels = _population(n=1500, seed=7, with_signal=with_signal)
    pack = load_rule_pack("rule_packs/payments_v1.3.0.yaml")

    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        trail = AuditTrail(os.path.join(d, "trail.jsonl"), tenant_id="demo-tenant")
        config = RunConfig(
            tenant_id="demo-tenant",
            policy=SamplingPolicy(policy_version="v1", tolerable_misstatement=100_000, random_control_size=20),
            rule_pack=pack,
            risk_weights=RiskWeights.without_labels(),
            ensemble_config=EnsembleConfig(),
            run_id=f"run-{label}",
        )
        result = run_pipeline(df, config, trail)

    benchmark = benchmark_ranking(result.risk_scores, labels, k_fraction=0.10, bootstrap_iterations=1000, seed=0)
    print(f"=== {label} ===")
    print(benchmark.statement())
    print()
    return benchmark.verdict


def main() -> None:
    signal_verdict = _run("signal case", with_signal=True)
    no_signal_verdict = _run("no-signal case", with_signal=False)

    assert signal_verdict == "BEATS_RANDOM", f"expected BEATS_RANDOM, got {signal_verdict}"
    assert no_signal_verdict in ("NOT_DISTINGUISHABLE_FROM_RANDOM", "INSUFFICIENT_DATA"), (
        f"expected NOT_DISTINGUISHABLE_FROM_RANDOM, got {no_signal_verdict}"
    )
    print("pipeline_demo.py: OK")


if __name__ == "__main__":
    main()
