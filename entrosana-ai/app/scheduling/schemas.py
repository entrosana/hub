"""Pydantic schemas for scheduling."""

from datetime import datetime

from pydantic import BaseModel


class ScheduleIn(BaseModel):
    name: str


class ScheduleOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
