"""Encrypted per-tenant credential storage.

Credential values are encrypted at the application layer before they are
written to `TenantProviderCredential.encrypted_value`. Decryption requires the
same Fernet key (derived from `tenant_credential_encryption_key` or as a
fallback from `secret_key`).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.providers.bindings import get_tenant_binding
from app.providers.models import TenantProviderCredential

_KEY_INFO = b"tenant-credential@entrosana.ai"


@lru_cache(maxsize=1)
def _get_key() -> bytes:
    """Derive a 32-byte Fernet key from the configured secret."""
    raw = settings.tenant_credential_encryption_key or settings.secret_key
    if not raw:
        raise RuntimeError("encryption key not configured")
    return base64.urlsafe_b64encode(
        HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_KEY_INFO).derive(raw.encode())
    )


def _fernet() -> Fernet:
    return Fernet(_get_key())


def encrypt_credential(value: str) -> str:
    """Encrypt a credential value for storage."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_credential(token: str) -> str:
    """Decrypt a credential value back to plaintext."""
    return _fernet().decrypt(token.encode()).decode()


async def _provider_for_tenant(db: AsyncSession, tenant_id: UUID | str) -> str:
    """Resolve the effective provider for a tenant from DB first, then settings.

    This mirrors the logic in `FallbackBindingSource` while staying free of
    an async dependency so the encryption helpers can be reused easily.
    """
    db_provider = await get_tenant_binding(db, tenant_id)
    if db_provider is not None:
        return db_provider
    configured = settings.accounting_provider_bindings or {}
    return configured.get(str(tenant_id), settings.default_accounting_provider)


async def get_tenant_credentials(db: AsyncSession, tenant_id: UUID | str) -> dict[str, str]:
    """Return decrypted, provider-scoped credentials for a tenant.

    If no DB row exists an empty dict is returned; the executor will fall back
    to per-tenant or global settings secrets.
    """
    provider_name = await _provider_for_tenant(db, tenant_id)
    result = await db.execute(
        select(TenantProviderCredential).where(
            TenantProviderCredential.tenant_id == tenant_id,
            TenantProviderCredential.provider_name == provider_name,
        )
    )
    rows = result.scalars().all()
    return {row.setting_name: decrypt_credential(row.encrypted_value) for row in rows}


async def set_tenant_credential(
    db: AsyncSession,
    tenant_id: UUID | str,
    provider_name: str,
    setting_name: str,
    value: str,
) -> TenantProviderCredential:
    """Store (or update) one encrypted credential for a tenant."""
    encrypted = encrypt_credential(value)
    result = await db.execute(
        select(TenantProviderCredential).where(
            TenantProviderCredential.tenant_id == tenant_id,
            TenantProviderCredential.provider_name == provider_name,
            TenantProviderCredential.setting_name == setting_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.encrypted_value = encrypted
        return existing

    credential = TenantProviderCredential(
        tenant_id=tenant_id,
        provider_name=provider_name,
        setting_name=setting_name,
        encrypted_value=encrypted,
    )
    db.add(credential)
    await db.flush()
    return credential


async def set_tenant_credentials(
    db: AsyncSession,
    tenant_id: UUID | str,
    provider_name: str,
    credentials: dict[str, str],
) -> list[TenantProviderCredential]:
    """Bulk-store encrypted credentials for a tenant."""
    return [
        await set_tenant_credential(db, tenant_id, provider_name, name, value)
        for name, value in credentials.items()
    ]
