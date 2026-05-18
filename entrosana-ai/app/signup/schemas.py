"""Pydantic schemas for signup."""
from datetime import datetime
from pydantic import BaseModel


class ApplicationIn(BaseModel):
    name: str


class ApplicationOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
