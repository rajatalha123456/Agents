"""
Minimal semver + `engine_compat` range checker (`">=1.0.0 <2.0.0"` style),
dependency-free on purpose so the pack loader has no supply-chain surface
beyond PyYAML + Pydantic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
_CLAUSE_RE = re.compile(r"(>=|<=|>|<|==)\s*(\d+\.\d+\.\d+)")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, s: str) -> "Version":
        m = _SEMVER_RE.match(s.strip())
        if not m:
            raise ValueError(f"not a valid semver: {s!r}")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))


_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def satisfies(version: str, constraint: str) -> bool:
    """
    e.g. satisfies("1.2.0", ">=1.0.0 <2.0.0") -> True

    Each whitespace-separated clause must hold (AND semantics, same as the
    manifest's `engine_compat` field in §5.1).
    """
    v = Version.parse(version)
    clauses = _CLAUSE_RE.findall(constraint)
    if not clauses:
        raise ValueError(f"unparseable engine_compat constraint: {constraint!r}")
    for op, bound in clauses:
        if not _OPS[op](v, Version.parse(bound)):
            return False
    return True
