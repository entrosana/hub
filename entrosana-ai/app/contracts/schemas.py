"""Pydantic schemas for contracts."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ContractStatus = Literal["draft", "sent", "signed", "void"]


class ContractIn(BaseModel):
    title: str
    template_version: str


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    template_version: str
    status: str
    signed_at: datetime | None
    created_at: datetime
