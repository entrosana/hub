"""ORM models for addresses (Swiss postal validation + geocoding)."""
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Address(TenantBase):
    __tablename__ = "addresses_records"

    line1: Mapped[str] = mapped_column(String(256))
    line2: Mapped[str | None] = mapped_column(String(256), nullable=True)
    postcode: Mapped[str] = mapped_column(String(16), index=True)
    city: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(2), default="CH")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
