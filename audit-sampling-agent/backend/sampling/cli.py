"""CLI: `sample` and `verify-trail` commands."""
from __future__ import annotations

import argparse
import json
import sys

from .audit_trail import AuditTrail
from .engine import SamplingPolicy, build_sample
from .ingestion import ingest


def _cmd_sample(args: argparse.Namespace) -> None:
    result = ingest(args.path, item_id_col=args.item_id_col, amount_col=args.amount_col)
    policy = SamplingPolicy(
        policy_version=args.policy_version,
        tolerable_misstatement=args.tolerable_misstatement,
        confidence_level=args.confidence_level,
        expected_misstatement=args.expected_misstatement,
        random_control_size=args.random_control_size,
    )
    sample_result = build_sample(
        result.frame, policy, item_id_col=args.item_id_col, amount_col=args.amount_col,
        user_seed=args.seed,
    )
    print(json.dumps(sample_result.summary(), indent=2, default=str))


def _cmd_verify_trail(args: argparse.Namespace) -> None:
    trail = AuditTrail(args.path, tenant_id=args.tenant_id)
    report = trail.verify()
    print(json.dumps(
        {
            "valid": report.valid,
            "first_invalid_sequence": report.first_invalid_sequence,
            "reason": report.reason,
            "events_checked": report.events_checked,
        },
        indent=2,
    ))
    sys.exit(0 if report.valid else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sampling")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample")
    p_sample.add_argument("path")
    p_sample.add_argument("--item-id-col", dest="item_id_col", default="item_id")
    p_sample.add_argument("--amount-col", dest="amount_col", default="amount")
    p_sample.add_argument("--policy-version", dest="policy_version", default="v1")
    p_sample.add_argument("--tolerable-misstatement", type=float, required=True)
    p_sample.add_argument("--confidence-level", type=float, default=0.95)
    p_sample.add_argument("--expected-misstatement", type=float, default=0.0)
    p_sample.add_argument("--random-control-size", type=int, default=0)
    p_sample.add_argument("--seed", default=None)
    p_sample.set_defaults(func=_cmd_sample)

    p_verify = sub.add_parser("verify-trail")
    p_verify.add_argument("path")
    p_verify.add_argument("--tenant-id", dest="tenant_id", required=True)
    p_verify.set_defaults(func=_cmd_verify_trail)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
