"""ORM models for signup (student enrolment flow)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Application(TenantBase):
    __tablename__ = "signup_applications"

    student_name: Mapped[str] = mapped_column(String(256))
    parent_name: Mapped[str] = mapped_column(String(256))
    parent_email: Mapped[str] = mapped_column(String(320), index=True)
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
