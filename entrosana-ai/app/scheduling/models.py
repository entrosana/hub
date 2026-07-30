"""ORM models for scheduling (class schedules, substitute matching)."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Schedule(TenantBase):
    __tablename__ = "scheduling_schedules"

    title: Mapped[str] = mapped_column(String(256))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    room: Mapped[str | None] = mapped_column(String(64), nullable=True)
