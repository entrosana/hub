"""ORM models for taxes (Swiss source tax, AHV/IV, year-end filings)."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Filing(TenantBase):
    __tablename__ = "taxes_filings"

    kind: Mapped[str] = mapped_column(String(64), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    period_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
