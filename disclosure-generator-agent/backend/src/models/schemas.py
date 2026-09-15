"""Pydantic schemas for signed calculation runs and the disclosure API.

The calculation payload models the kind of data a fund/portfolio calc engine
produces (NAV, returns, allocation, fees). Field names are intentionally
generic and `extra="allow"` on CalculationPayload so a real calc engine's
exact schema can be mapped onto this without forking the model — but no
field here is invented business logic; each maps to a value the calc engine
is expected to already produce.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Language(str, Enum):
    EN = "en"
    UR = "ur"
    AR = "ar"


class AllocationItem(BaseModel):
    category: str
    weight_percent: float


class FeeItem(BaseModel):
    name: str
    amount: float
    currency: str


class CalculationPayload(BaseModel):
    """The authoritative, signed output of the calculation engine.

    This is the single source of truth for every number that may appear
    in a generated disclosure. `extra="allow"` lets a real calc engine
    attach additional fields without breaking verification or the numeric
    guard (both operate over the full payload, known fields or not).
    """

    model_config = ConfigDict(extra="allow")

    account_id: str
    account_name: str
    currency: str
    period_start: date
    period_end: date
    nav: float
    opening_balance: float
    closing_balance: float
    return_percent: float
    allocation: list[AllocationItem]
    fees: list[FeeItem] = Field(default_factory=list)


class SignedRun(BaseModel):
    """A calculation run as signed by the trusted calc engine / signing service.

    Signing happens outside this application (see src/signing/sign.py, a
    reference implementation only). The Disclosure Generator only verifies.
    """

    run_id: str
    payload: CalculationPayload
    signature: str = Field(description="Base64-encoded Ed25519 signature")
    signature_algorithm: str = Field(default="Ed25519")
    signed_at: datetime


class DisclosureRequest(BaseModel):
    signed_run: SignedRun
    language: Language


class DisclosureStatus(str, Enum):
    SUCCESS = "success"
    REFUSED = "refused"


class VerificationInfo(BaseModel):
    signature_valid: bool
    freshness_valid: bool
    sanity_valid: bool


class DisclosureResponse(BaseModel):
    run_id: str
    language: Language
    status: DisclosureStatus
    disclosure: Optional[str] = None
    verification: VerificationInfo
    reason: Optional[str] = None
