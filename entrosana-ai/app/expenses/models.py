"""ORM models for expenses (submission, approval, reimbursement)."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Expense(TenantBase):
    __tablename__ = "expenses_expenses"

    description: Mapped[str] = mapped_column(String(512))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    receipt_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
