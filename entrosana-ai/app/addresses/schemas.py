"""Pydantic schemas for addresses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AddressIn(BaseModel):
    line1: str
    line2: str | None = None
    postcode: str
    city: str
    country: str = Field(default="CH", min_length=2, max_length=2)


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    line1: str
    line2: str | None
    postcode: str
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    created_at: datetime
