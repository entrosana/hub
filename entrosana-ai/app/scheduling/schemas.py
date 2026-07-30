"""Pydantic schemas for scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ScheduleIn(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    room: str | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    room: str | None
    created_at: datetime
