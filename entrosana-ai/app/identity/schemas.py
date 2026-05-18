"""Pydantic schemas for identity."""
from datetime import datetime
from pydantic import BaseModel


class UserIn(BaseModel):
    name: str


class UserOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
