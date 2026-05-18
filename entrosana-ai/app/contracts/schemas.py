"""Pydantic schemas for contracts."""
from datetime import datetime
from pydantic import BaseModel


class ContractIn(BaseModel):
    name: str


class ContractOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
