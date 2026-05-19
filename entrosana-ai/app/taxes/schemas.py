"""Pydantic schemas for taxes."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


FilingKind = Literal[
    "source_tax",   # Quellensteuer
    "ahv_iv",       # AHV / IV / EO
    "payroll_tax",
    "year_end",
]


class FilingIn(BaseModel):
    kind: FilingKind
    period_year: int
    period_month: int | None = None


class FilingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    kind: str
    period_year: int
    period_month: int | None
    status: str
    submitted_at: datetime | None
    created_at: datetime
