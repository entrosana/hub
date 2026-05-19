"""ORM models for documents (ingestion, OCR, classification)."""
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class Document(TenantBase):
    __tablename__ = "documents_documents"

    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    storage_uri: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    classification: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
