"""ORM models for admin (students, parents, staff, org hierarchy)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Person(TenantBase):
    __tablename__ = "admin_persons"

    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
