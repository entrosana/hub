"""Pydantic schemas for expenses."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExpenseIn(BaseModel):
    description: str
    amount_cents: int
    currency: str = "CHF"
    receipt_document_id: str | None = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    description: str
    amount_cents: int
    currency: str
    status: str
    receipt_document_id: str | None
    created_at: datetime
