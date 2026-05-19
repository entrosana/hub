"""Pydantic schemas for admin."""

from datetime import datetime

from pydantic import BaseModel


class PersonIn(BaseModel):
    name: str


class PersonOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
