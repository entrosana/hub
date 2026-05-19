"""Pydantic schemas for expenses."""

from datetime import datetime

from pydantic import BaseModel


class ExpenseIn(BaseModel):
    name: str


class ExpenseOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    created_at: datetime
