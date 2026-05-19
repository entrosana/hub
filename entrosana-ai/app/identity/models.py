"""ORM models for identity (tenants, users, roles)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class User(TenantBase):
    __tablename__ = "identity_users"

    name: Mapped[str] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
