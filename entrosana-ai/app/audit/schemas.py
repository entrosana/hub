"""Pydantic schemas for audit endpoints."""
from datetime import datetime
from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: int
    tenant_id: str
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
    first_bad_event_id: int | None = None
