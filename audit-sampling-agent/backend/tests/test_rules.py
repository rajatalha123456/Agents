import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from sampling.rules import (
    Rule,
    RulePack,
    RuleExpressionError,
    evaluate_expression,
    evaluate_rules,
    load_rule_pack,
)

RULE_PACK_PATH = Path(__file__).resolve().parents[1] / "rule_packs" / "payments_v1.3.0.yaml"


def test_pack_loads_and_evaluates():
    pack = load_rule_pack(str(RULE_PACK_PATH))
    assert pack.pack_id == "payments"
    df = pd.DataFrame({
        "amount": [60000.0, 100.0],
        "approver_count": [1, 2],
        "posting_hour": [10, 10],
        "vendor_is_new": [0, 0],
        "vendor_transaction_count_30d": [1, 1],
    })
    result = evaluate_rules(df, pack, as_of=dt.date(2025, 6, 1))
    assert result.scores[0] == 100  # critical: single_approval_authority_breach
    assert result.scores[1] == 0


def test_effective_dating_excludes_superseded_at_today():
    pack = load_rule_pack(str(RULE_PACK_PATH))
    in_force_today = {r.rule_id for r in pack.in_force(dt.date(2025, 1, 1))}
    assert "single_approval_authority_breach_legacy" not in in_force_today
    in_force_2023 = {r.rule_id for r in pack.in_force(dt.date(2023, 6, 1))}
    assert "single_approval_authority_breach_legacy" in in_force_2023


def test_score_is_max_not_sum():
    pack = RulePack(
        pack_id="test", pack_version="1.0.0",
        rules=(
            Rule("low1", "d", "amount > 0", "low", "o", "e", dt.date(2020, 1, 1)),
            Rule("crit1", "d", "amount > 0", "critical", "o", "e", dt.date(2020, 1, 1)),
        ),
    )
    df = pd.DataFrame({"amount": [100.0]})
    result = evaluate_rules(df, pack)
    assert result.scores[0] == 100  # not 120


def test_missing_column_skips_not_zero_score():
    pack = RulePack(
        pack_id="test", pack_version="1.0.0",
        rules=(
            Rule("r1", "d", "missing_col > 0", "high", "o", "e", dt.date(2020, 1, 1),
                 required_columns=("missing_col",)),
        ),
    )
    df = pd.DataFrame({"amount": [100.0]})
    result = evaluate_rules(df, pack)
    assert "r1" in result.skipped_rules
    assert any("skipped" in w for w in result.warnings)


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "open('x.txt')",
    "amount.__class__",
])
def test_forbidden_constructs_raise(expr):
    df = pd.DataFrame({"amount": [100.0]})
    with pytest.raises(RuleExpressionError):
        evaluate_expression(expr, df)


def test_allowed_grammar_works():
    df = pd.DataFrame({"amount": [100.0, -50.0, 0.0]})
    result = evaluate_expression("(amount > 0) and (amount < 200)", df)
    assert list(result) == [True, False, False]


def test_allowed_functions_work():
    df = pd.DataFrame({"amount": [-100.0, 50.0]})
    result = evaluate_expression("abs(amount) > 60", df)
    assert list(result) == [True, False]


def test_chained_comparison_raises():
    df = pd.DataFrame({"amount": [100.0]})
    with pytest.raises(RuleExpressionError):
        evaluate_expression("0 < amount < 200", df)


def test_unknown_column_raises():
    df = pd.DataFrame({"amount": [100.0]})
    with pytest.raises(RuleExpressionError):
        evaluate_expression("nonexistent > 0", df)
