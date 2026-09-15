"""Money fields are strings in JSON (section 6.2) -- never floats -- so the
frontend must parse with a decimal library, never parseFloat.
"""
from __future__ import annotations

from decimal import Decimal


def money_str(value) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)))
