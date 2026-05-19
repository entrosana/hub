"""Pydantic schemas for addresses."""

from datetime import datetime

from pydantic import BaseModel


class AddressIn(BaseModel):
    name: str


class AddressOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
