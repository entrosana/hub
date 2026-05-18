"""Pydantic schemas for documents."""
from datetime import datetime
from pydantic import BaseModel


class DocumentIn(BaseModel):
    name: str


class DocumentOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
