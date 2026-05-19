"""Pydantic schemas for admin."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


PersonKind = Literal["student", "parent", "staff"]


class PersonIn(BaseModel):
    name: str
    kind: PersonKind
    email: EmailStr | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    kind: str
    email: str | None
    created_at: datetime
