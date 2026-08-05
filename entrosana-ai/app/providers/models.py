"""DB models for provider-layer configuration.

`TenantProviderCredential` stores encrypted per-tenant secrets used by the
executor. `TenantProviderBinding` stores the active provider selection.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, UniqueConstraint
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


class TenantProviderBinding(TenantBase):
    """The active provider selection for one tenant."""

    __tablename__ = "providers_tenant_bindings"

    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_providers_tenant_bindings_tenant"),)
