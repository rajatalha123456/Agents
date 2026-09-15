"""Versioned, effective-dated rule packs with a safe expression grammar.

Never uses eval(). Expressions are parsed with ast and walked, permitting
only a small whitelisted grammar.
"""
from __future__ import annotations

import ast
import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

_SEVERITY_SCORES = {"critical": 100, "high": 75, "medium": 45, "low": 20}

_ALLOWED_CALLS = {"abs": np.abs, "log": np.log, "round": np.round}


class RuleExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    expression: str
    severity: str
    owner: str
    explanation: str
    effective_from: dt.date
    effective_to: dt.date | None = None
    required_columns: tuple[str, ...] = field(default_factory=tuple)

    def in_force(self, as_of: dt.date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True

    @property
    def severity_score(self) -> int:
        return _SEVERITY_SCORES[self.severity]


@dataclass(frozen=True)
class RulePack:
    pack_id: str
    pack_version: str
    rules: tuple[Rule, ...]

    def in_force(self, as_of: dt.date | None = None) -> tuple[Rule, ...]:
        as_of = as_of or dt.date.today()
        return tuple(r for r in self.rules if r.in_force(as_of))


@dataclass(frozen=True)
class RuleResult:
    fired: pd.DataFrame  # index-aligned boolean per rule per row
    scores: np.ndarray
    fired_rules_by_row: list[list[dict]]
    skipped_rules: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _parse_date(value) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def load_rule_pack(path: str) -> RulePack:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    rules = []
    for r in raw["rules"]:
        rules.append(
            Rule(
                rule_id=r["rule_id"],
                description=r["description"],
                expression=r["expression"],
                severity=r["severity"],
                owner=r.get("owner", "unknown"),
                explanation=r.get("explanation", ""),
                effective_from=_parse_date(r["effective_from"]),
                effective_to=_parse_date(r["effective_to"]) if r.get("effective_to") else None,
                required_columns=tuple(r.get("required_columns", [])),
            )
        )
    return RulePack(pack_id=raw["pack_id"], pack_version=raw["pack_version"], rules=tuple(rules))


class _SafeEvaluator(ast.NodeVisitor):
    """Walks a restricted AST and evaluates it against a DataFrame's columns."""

    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def visit(self, node):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor is None:
            raise RuleExpressionError(f"disallowed expression element: {node.__class__.__name__}")
        return visitor(node)

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_BoolOp(self, node: ast.BoolOp):
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            result = values[0]
            for v in values[1:]:
                result = result & v
            return result
        elif isinstance(node.op, ast.Or):
            result = values[0]
            for v in values[1:]:
                result = result | v
            return result
        raise RuleExpressionError("unsupported boolean operator")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return ~operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise RuleExpressionError("unsupported unary operator")

    def visit_Compare(self, node: ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise RuleExpressionError("chained comparisons are not allowed")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        raise RuleExpressionError("unsupported comparison operator")

    def visit_BinOp(self, node: ast.BinOp):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise RuleExpressionError("unsupported binary operator")

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
            raise RuleExpressionError("only abs(), log(), round() calls are permitted")
        if node.keywords:
            raise RuleExpressionError("keyword arguments are not permitted")
        args = [self.visit(a) for a in node.args]
        return _ALLOWED_CALLS[node.func.id](*args)

    def visit_Name(self, node: ast.Name):
        if node.id not in self.frame.columns:
            raise RuleExpressionError(f"unknown column '{node.id}'")
        return self.frame[node.id]

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float, bool, str)) or node.value is None:
            return node.value
        raise RuleExpressionError("unsupported constant type")


def evaluate_expression(expression: str, frame: pd.DataFrame):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RuleExpressionError(f"invalid expression syntax: {exc}") from exc
    evaluator = _SafeEvaluator(frame)
    result = evaluator.visit(tree)
    if isinstance(result, pd.Series):
        return result.to_numpy(dtype=bool)
    return np.full(len(frame), bool(result))


def evaluate_rules(frame: pd.DataFrame, pack: RulePack, as_of: dt.date | None = None) -> RuleResult:
    as_of = as_of or dt.date.today()
    in_force = pack.in_force(as_of)

    n = len(frame)
    fired_cols = {}
    skipped = []
    warnings = []

    for rule in in_force:
        missing = [c for c in rule.required_columns if c not in frame.columns]
        if missing:
            skipped.append(rule.rule_id)
            warnings.append(
                f"rule '{rule.rule_id}' skipped: missing required column(s) "
                f"{missing} -- this is a coverage gap, not a clean result."
            )
            fired_cols[rule.rule_id] = np.zeros(n, dtype=bool)
            continue
        try:
            fired_cols[rule.rule_id] = evaluate_expression(rule.expression, frame)
        except RuleExpressionError as exc:
            skipped.append(rule.rule_id)
            warnings.append(f"rule '{rule.rule_id}' skipped: {exc}")
            fired_cols[rule.rule_id] = np.zeros(n, dtype=bool)

    fired_df = pd.DataFrame(fired_cols, index=frame.index)

    scores = np.zeros(n)
    fired_rules_by_row: list[list[dict]] = [[] for _ in range(n)]
    for rule in in_force:
        if rule.rule_id in skipped:
            continue
        mask = fired_df[rule.rule_id].to_numpy()
        scores = np.where(mask & (rule.severity_score > scores), rule.severity_score, scores)
        for i in np.nonzero(mask)[0]:
            fired_rules_by_row[i].append(
                {
                    "rule_id": rule.rule_id,
                    "severity": rule.severity,
                    "description": rule.description,
                    "explanation": rule.explanation,
                    "owner": rule.owner,
                }
            )

    return RuleResult(
        fired=fired_df,
        scores=scores,
        fired_rules_by_row=fired_rules_by_row,
        skipped_rules=tuple(skipped),
        warnings=tuple(warnings),
    )
