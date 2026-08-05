"""DB models for provider-layer configuration.

`TenantProviderCredential` stores encrypted per-tenant secrets used by the
executor. Bindings (which provider a tenant runs) are still settings-backed for
now; this table is the first half of the DB-backed configuration (ADR 0002).
"""

from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import TenantBase


class TenantProviderCredential(TenantBase):
    """One encrypted tenant/provider/setting row.

    The value is encrypted at the application layer (Fernet via HKDF) before
    it reaches the DB so a compromised schema dump cannot reveal raw secrets.
    """

    __tablename__ = "providers_tenant_credentials"

    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    setting_name: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider_name",
            "setting_name",
            name="uq_providers_tenant_credentials_tenant_provider_setting",
        ),
    )
