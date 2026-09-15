from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TenantScoped, TimestampMixin, UUIDPk


class JournalDraftStatus(str, enum.Enum):
    """
    §14.1 — Agent drafts, Maker submits, Checker approves, System posts.
    The agent can only ever produce rows in DRAFT status; every later
    transition is a human or system action. There is no `post_journal`
    tool (§12.3) — POSTED is set by the platform's posting service, never
    by agent code.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    POSTED = "POSTED"


class JournalDraft(Base, UUIDPk, TenantScoped, TimestampMixin):
    """§4.2 / EP-07 — internal subledger draft. `template_id` from the pack's journal template registry."""

    __tablename__ = "journal_draft"

    break_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("break_case.id"), nullable=False, index=True
    )
    template_id: Mapped[str] = mapped_column(String, nullable=False)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[JournalDraftStatus] = mapped_column(
        Enum(JournalDraftStatus, name="journal_draft_status"), default=JournalDraftStatus.DRAFT
    )
    posted_by: Mapped[str | None] = mapped_column(String, nullable=True)  # always a human actor id
    submitted_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
