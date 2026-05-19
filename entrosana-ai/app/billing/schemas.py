"""Pydantic schemas for billing."""

from datetime import datetime

from pydantic import BaseModel


class InvoiceIn(BaseModel):
    name: str


class InvoiceOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
