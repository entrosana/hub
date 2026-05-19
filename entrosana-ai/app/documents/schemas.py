"""Pydantic schemas for documents."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentIn(BaseModel):
    filename: str
    mime_type: str
    storage_uri: str
    size_bytes: int


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    filename: str
    mime_type: str
    storage_uri: str
    size_bytes: int
    classification: str | None
    status: str
    created_at: datetime
