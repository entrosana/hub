"""Audit ORM models — signed append-only chain + DLM interaction log."""

from uuid import UUID

from sqlalchemy import JSON, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class AuditEvent(TenantBase):
    """One signed mutation in the per-tenant chain.

    `seq` is a monotonic per-tenant sequence (1..N) that is part of the signed
    payload and is what the chain is ordered/verified by — never wall-clock
    `created_at`. `UNIQUE(tenant_id, seq)` makes a concurrent fork (two events
    claiming the same slot) fail instead of silently corrupting the chain.
    `key_id` records which HMAC key signed the row so keys can be rotated.
    """

    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("tenant_id", "seq", name="uq_audit_tenant_seq"),)

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    before_state: Mapped[dict] = mapped_column(JSON, default=dict)
    after_state: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_hmac: Mapped[str] = mapped_column(String(64))
    hmac: Mapped[str] = mapped_column(String(64), index=True)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False, server_default="k1")


class AuditChainHead(TenantBase):
    """Anchored head of a tenant's chain: the highest `seq` and its hmac.

    Updated in the same transaction as each append (under a row lock). Verify
    checks the walked chain's length/head against this anchor, so deleting rows
    from the END of the chain (tail-truncation) is detected — the surviving
    prefix is internally consistent but no longer matches the anchor.
    One row per tenant.
    """

    __tablename__ = "audit_chain_head"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_audit_head_tenant"),)

    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    head_hmac: Mapped[str] = mapped_column(String(64), nullable=False)


class AuditChainCheckpoint(TenantBase):
    """Previously verified prefix boundary for a tenant's audit chain."""

    __tablename__ = "audit_chain_checkpoint"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_audit_checkpoint_tenant"),)

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    hmac: Mapped[str] = mapped_column(String(64), nullable=False)


class AuditEventArchive(TenantBase):
    """Cold storage for audit events covered by a verified checkpoint."""

    __tablename__ = "audit_events_archive"
    __table_args__ = (UniqueConstraint("tenant_id", "seq", name="uq_audit_archive_tenant_seq"),)

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    before_state: Mapped[dict] = mapped_column(JSON, default=dict)
    after_state: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_hmac: Mapped[str] = mapped_column(String(64))
    hmac: Mapped[str] = mapped_column(String(64), index=True)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False, server_default="k1")


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
