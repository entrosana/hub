"""Pydantic schemas for accounting."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntryIn(BaseModel):
    description: str
    amount_cents: int
    currency: str = "CHF"


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    description: str
    amount_cents: int
    currency: str
    status: str = Field(description="proposed | approved | posted | voided")
    created_at: datetime
