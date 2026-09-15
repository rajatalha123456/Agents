from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class ProposalKind(str, enum.Enum):
    """§11.3 — the closed set of things the agent may propose. Nothing here executes."""

    MATCH = "MATCH"
    SPLIT = "SPLIT"
    JOURNAL_DRAFT = "JOURNAL_DRAFT"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    INFO_REQUEST = "INFO_REQUEST"
    CARRY_FORWARD = "CARRY_FORWARD"
    ESCALATE = "ESCALATE"
    SUPPRESS_RULE = "SUPPRESS_RULE"
    NO_PROPOSAL = "NO_PROPOSAL"


class ProposalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"


class Proposal(Base, UUIDPk, TenantScoped, TimestampMixin):
    """
    §4.2 — the agent's recommendation. Only ever written by the
    `create_proposal` draft-only tool (§12.2), status always starts DRAFT.

    A proposal that fails §11.2 step 8 validation is never persisted at
    all — there is deliberately no "invalid" status; see
    core/agent/validators.py.
    """

    __tablename__ = "proposal"

    break_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("break_case.id"), nullable=False, index=True
    )
    kind: Mapped[ProposalKind] = mapped_column(Enum(ProposalKind, name="proposal_kind"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[str | None] = mapped_column(Numeric(6, 5), nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus, name="proposal_status"), default=ProposalStatus.DRAFT
    )
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)


class EvidenceItem(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 — support for a proposal. Written only via `attach_evidence` (§12.2)."""

    __tablename__ = "evidence_item"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposal.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)  # EP-10 evidence type registry
    ref_type: Mapped[str] = mapped_column(String, nullable=False)
    ref_id: Mapped[str] = mapped_column(String, nullable=False)
    snippet: Mapped[str | None] = mapped_column(String, nullable=True)
    retrieval_score: Mapped[str | None] = mapped_column(Numeric(6, 5), nullable=True)


class Decision(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 — a human's decision on a case/proposal. Never made by the agent."""

    __tablename__ = "decision"

    break_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("break_case.id"), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String, nullable=False)  # human actor id, never "AGENT"
    action: Mapped[str] = mapped_column(String, nullable=False)  # approve/reject/return/escalate
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    prior_status: Mapped[str] = mapped_column(String, nullable=False)
    new_status: Mapped[str] = mapped_column(String, nullable=False)
