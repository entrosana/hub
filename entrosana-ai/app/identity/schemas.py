"""Pydantic schemas for identity."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserIn(BaseModel):
    name: str
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    email: str | None
    created_at: datetime
