"""ORM models for billing (family-based invoicing, sibling discounts)."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Invoice(TenantBase):
    __tablename__ = "billing_invoices"

    number: Mapped[str] = mapped_column(String(32), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
