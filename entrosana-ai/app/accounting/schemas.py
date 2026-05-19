"""Pydantic schemas for accounting."""

from datetime import datetime

from pydantic import BaseModel


class EntryIn(BaseModel):
    name: str


class EntryOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
