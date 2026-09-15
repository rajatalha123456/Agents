"""
§7.2 — row fingerprint for duplicate detection.

    row_fingerprint = sha256(
        account_ref || amount || currency || value_date ||
        reference_canonical || counterparty_id || direction
    )

A duplicate fingerprint is a *flag*, never an automatic delete (§7.2) — this
module only computes the hash; what a caller does with a collision (human
decision, DUP-01/DUP-02 break) is an ingestion/matching concern.
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from core.models.canonical_record import Direction

_SEP = "\x1f"  # unlikely to appear in any source field; avoids ambiguous concatenation


def compute_row_fingerprint(
    *,
    account_ref: str,
    amount: Decimal,
    currency: str,
    value_date: date,
    reference_canonical: str | None,
    counterparty_id: str | None,
    direction: Direction,
) -> str:
    parts = [
        account_ref,
        format(amount, "f"),
        currency,
        value_date.isoformat(),
        reference_canonical or "",
        counterparty_id or "",
        direction.value,
    ]
    payload = _SEP.join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
