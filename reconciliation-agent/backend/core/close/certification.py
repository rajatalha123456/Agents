"""§15.3 — certification blocking rules. Certification is a human/system
action; the agent has no `certify` tool (§12.3, §15.4) — this module only
decides whether a human *may* certify, never performs the certification
itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CertificationBlocker:
    reason: str


@dataclass(frozen=True)
class AccountCertificationFacts:
    account_ref: str
    unexplained: Decimal
    has_high_risk_open_break: bool
    has_break_aged_past_policy_limit: bool


def evaluate_certification(
    accounts: list[AccountCertificationFacts],
    unexplained_threshold: Decimal,
) -> list[CertificationBlocker]:
    """§15.3: certification is blocked if unexplained balance exceeds
    threshold, OR a high-risk break is open, OR an item is aged beyond the
    policy limit — on any account in the period. Returns every blocker
    found (not just the first) so the reviewer sees the whole picture.
    """
    blockers: list[CertificationBlocker] = []
    for account in accounts:
        if abs(account.unexplained) > unexplained_threshold:
            blockers.append(CertificationBlocker(
                f"{account.account_ref}: unexplained balance {account.unexplained} exceeds threshold {unexplained_threshold}"
            ))
        if account.has_high_risk_open_break:
            blockers.append(CertificationBlocker(f"{account.account_ref}: high-risk break is open"))
        if account.has_break_aged_past_policy_limit:
            blockers.append(CertificationBlocker(f"{account.account_ref}: an aged item exceeds the policy limit"))
    return blockers


def can_certify(accounts: list[AccountCertificationFacts], unexplained_threshold: Decimal) -> bool:
    return not evaluate_certification(accounts, unexplained_threshold)
