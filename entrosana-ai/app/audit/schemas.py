"""Pydantic schemas for audit endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    actor_id: str
    action: str
    target_type: str
    target_id: str
    reasoning: str | None
    hmac: str
    created_at: datetime


class ChainVerificationResult(BaseModel):
    ok: bool
    events_checked: int
    first_bad_event_id: UUID | None = None
