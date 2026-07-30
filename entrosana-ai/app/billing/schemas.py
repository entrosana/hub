"""Pydantic schemas for billing."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvoiceIn(BaseModel):
    number: str
    family_id: str
    amount_cents: int
    currency: str = "CHF"
    issued_on: date
    due_on: date


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    number: str
    family_id: str
    amount_cents: int
    currency: str
    issued_on: date
    due_on: date
    status: str
    paid_at: datetime | None
    created_at: datetime
