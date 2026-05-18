"""Pydantic schemas for taxes."""
from datetime import datetime
from pydantic import BaseModel


class FilingIn(BaseModel):
    name: str


class FilingOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
