"""Standalone demo: build a MUS + random-control + high-risk sample over a
synthetic population and print the workpaper-style summary.

Run: python demo.py
"""
import numpy as np
import pandas as pd

from sampling.engine import SamplingPolicy, build_sample


def main() -> None:
    rng = np.random.default_rng(42)
    n = 2000
    ids = [f"TXN{i:06d}" for i in range(n)]
    amounts = np.round(rng.exponential(1500, n), 2)
    amounts[10] = 120_000.0  # a certainty item
    amounts[20] = -750.0     # a credit balance
    amounts[30] = 0.0        # a zero balance
    risk_score = rng.uniform(0, 100, n)

    df = pd.DataFrame({"item_id": ids, "amount": amounts, "risk_score": risk_score})

    policy = SamplingPolicy(
        policy_version="demo-v1",
        tolerable_misstatement=75_000,
        confidence_level=0.95,
        expected_misstatement=5_000,
        random_control_size=15,
        high_risk_threshold=95,
        test_negative_balances_100pct=True,
        review_zero_balances=True,
    )

    result = build_sample(df, policy, risk_col="risk_score", user_seed="demo-seed")

    print("=== Sampling run summary ===")
    for name, stratum in result.strata.items():
        s = stratum.summary()
        print(f"- {name}: {s['items_count']} items, projectable={s['projectable']}, "
              f"population_value={s['population_value']}")

    print("\nWarnings:")
    for w in result.warnings:
        print(f"  - {w}")

    print(f"\nDataset fingerprint: {result.manifest['dataset_fingerprint']}")
    print(f"Total book value: {result.manifest['book_value']:,.2f}")


if __name__ == "__main__":
    main()
