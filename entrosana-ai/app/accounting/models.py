"""ORM models for accounting (GL entries, booking proposals)."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Entry(TenantBase):
    __tablename__ = "accounting_entries"

    description: Mapped[str] = mapped_column(String(512))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
