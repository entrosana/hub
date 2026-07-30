"""Pydantic schemas for signup."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class ApplicationIn(BaseModel):
    student_name: str
    parent_name: str
    parent_email: EmailStr


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    student_name: str
    parent_name: str
    parent_email: str
    status: str
    created_at: datetime
