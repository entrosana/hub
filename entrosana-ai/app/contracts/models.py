"""ORM models for contracts (templates, signing flow, versioning)."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Contract(TenantBase):
    __tablename__ = "contracts_contracts"

    title: Mapped[str] = mapped_column(String(256))
    template_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
