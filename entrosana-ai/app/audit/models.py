"""Audit ORM models — signed append-only chain + DLM interaction log."""

from uuid import UUID

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class AuditEvent(TenantBase):
    """One signed mutation in the per-tenant chain."""

    __tablename__ = "audit_events"

    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    before_state: Mapped[dict] = mapped_column(JSON, default=dict)
    after_state: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_hmac: Mapped[str] = mapped_column(String(64))
    hmac: Mapped[str] = mapped_column(String(64), index=True)


class DLMInteraction(TenantBase):
    """One Deterministic-Language-Model call. Replayable, pinned, signed."""

    __tablename__ = "dlm_interactions"

    audit_event_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    temperature: Mapped[float] = mapped_column(default=0.0)
    input_payload: Mapped[dict] = mapped_column(JSON)
    output_payload: Mapped[dict] = mapped_column(JSON)
    retrieval_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    hmac: Mapped[str] = mapped_column(String(64))
