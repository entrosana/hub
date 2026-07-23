"""ORM models for identity (tenants, users, roles)."""

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class User(TenantBase):
    __tablename__ = "identity_users"

    name: Mapped[str] = mapped_column(String(256))
    # Email is the global login identifier, so it is globally unique. Nullable
    # is fine: users without a login (service accounts) are allowed, and both
    # Postgres and SQLite permit multiple NULLs under a UNIQUE column.
    email: Mapped[str | None] = mapped_column(String(320), index=True, unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Authorization role: "admin" (privileged/admin routes) or "member" (default).
    role: Mapped[str] = mapped_column(
        String(32), default="member", server_default="member", nullable=False
    )
    # Deactivated users cannot authenticate.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
