"""§4.2 EP-02 — break type is a registry (data), never an enum, so a pack
can add its own codes without touching core. This module only knows the
*mechanism* — look up a code, read its risk/sensitivity flags — never a
specific code's meaning (that would violate §2.2).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakTypeInfo:
    code: str
    family: str
    risk_weight: int
    is_sensitive: bool


class UnknownBreakType(ValueError):
    pass


class BreakTypeRegistry:
    """In-memory lookup over rows loaded from the `break_type` table /
    pack manifests (§5.1 `break_types`). Kept separate from the ORM so
    matching/classification code can be unit-tested without a database.
    """

    def __init__(self, entries: list[BreakTypeInfo]):
        by_code = {}
        for entry in entries:
            if entry.code in by_code:
                raise ValueError(f"duplicate break type code: {entry.code}")
            by_code[entry.code] = entry
        self._by_code = by_code

    def get(self, code: str) -> BreakTypeInfo:
        try:
            return self._by_code[code]
        except KeyError:
            raise UnknownBreakType(code) from None

    def is_sensitive(self, code: str) -> bool:
        return self.get(code).is_sensitive

    def risk_weight(self, code: str) -> int:
        return self.get(code).risk_weight


def isolating_dimensions_match(
    side_a_dimensions: dict[str, object],
    side_b_dimensions: dict[str, object],
    isolating_keys: list[str],
) -> bool:
    """§4.1/§4.4 — a match group spanning an isolating dimension (e.g. two
    different pools in the Mizan pack) must never be created. Core doesn't
    know what the dimension *means*; it only knows that when a key is
    flagged `is_isolating` in the dimension registry, both sides must carry
    the same value for that key (or both omit it) before a match is legal.
    """
    for key in isolating_keys:
        if side_a_dimensions.get(key) != side_b_dimensions.get(key):
            return False
    return True
