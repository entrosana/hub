"""Encrypted tenant credential storage (ADR 0002 — DB-backed credentials).

Covers: encryption round-trip (value is never stored in plaintext), tenant
isolation (one tenant's rows never leak into another's), upsert semantics,
settings fallback when no DB row exists, and executor integration (the
executor authenticates with the tenant's decrypted DB credential).
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select

from app.providers.credentials import (
    decrypt_credential,
    encrypt_credential,
    get_tenant_credentials,
    set_tenant_credential,
    set_tenant_credentials,
)
from app.providers.fake import FakeCashCtrlTransport
from app.providers.models import TenantProviderCredential
from app.providers.registry import get_registry


def test_encrypt_decrypt_round_trip():
    value = secrets.token_urlsafe(24)
    token = encrypt_credential(value)
    assert token != value
    assert value not in token
    assert decrypt_credential(token) == value


def test_encrypt_is_non_deterministic():
    value = secrets.token_urlsafe(24)
    assert encrypt_credential(value) != encrypt_credential(value)


async def test_stored_value_is_encrypted_at_rest(db):
    t = uuid.uuid4()
    value = secrets.token_urlsafe(24)
    await set_tenant_credential(db, t, "cashctrl", "cashctrl_api_key", value)
    await db.commit()

    row = (
        await db.execute(
            select(TenantProviderCredential).where(TenantProviderCredential.tenant_id == t)
        )
    ).scalar_one()
    assert row.encrypted_value != value
    assert value not in row.encrypted_value
    assert decrypt_credential(row.encrypted_value) == value


async def test_get_returns_decrypted_credentials(db):
    t = uuid.uuid4()
    key = secrets.token_urlsafe(24)
    await set_tenant_credentials(
        db, t, "cashctrl", {"cashctrl_api_key": key, "cashctrl_api_base": "https://t.example"}
    )
    await db.commit()

    creds = await get_tenant_credentials(db, t)
    assert creds == {"cashctrl_api_key": key, "cashctrl_api_base": "https://t.example"}


async def test_tenant_isolation(db):
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    k1, k2 = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    await set_tenant_credential(db, t1, "cashctrl", "cashctrl_api_key", k1)
    await set_tenant_credential(db, t2, "cashctrl", "cashctrl_api_key", k2)
    await db.commit()

    assert (await get_tenant_credentials(db, t1))["cashctrl_api_key"] == k1
    assert (await get_tenant_credentials(db, t2))["cashctrl_api_key"] == k2
    assert await get_tenant_credentials(db, uuid.uuid4()) == {}


async def test_set_credential_upserts(db):
    t = uuid.uuid4()
    await set_tenant_credential(db, t, "cashctrl", "cashctrl_api_key", "old-value-rotated")
    await set_tenant_credential(db, t, "cashctrl", "cashctrl_api_key", "new-value-rotated")
    await db.commit()

    rows = (
        (
            await db.execute(
                select(TenantProviderCredential).where(TenantProviderCredential.tenant_id == t)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert (await get_tenant_credentials(db, t))["cashctrl_api_key"] == "new-value-rotated"


async def test_credentials_scoped_to_bound_provider(db):
    """Rows for another provider must not leak into the tenant's executor."""
    t = uuid.uuid4()
    await set_tenant_credential(db, t, "bexio", "bexio_api_key", secrets.token_urlsafe(24))
    await db.commit()

    assert await get_tenant_credentials(db, t) == {}  # tenant is bound to cashctrl


async def test_registry_credentials_fall_back_to_settings_without_session():
    creds = await get_registry().credentials_for_tenant(uuid.uuid4())
    assert creds == {}


async def test_executor_uses_db_credential(db):
    t = uuid.uuid4()
    key = secrets.token_urlsafe(24)
    await set_tenant_credentials(
        db,
        t,
        "cashctrl",
        {"cashctrl_api_key": key, "cashctrl_api_base": "https://tenant.cashctrl.test"},
    )
    await db.commit()

    executor = await get_registry().executor_for_tenant(t, FakeCashCtrlTransport(), session=db)
    assert executor._credential_overrides["cashctrl_api_key"] == key
    assert executor._secret("cashctrl_api_key") == key
    r = await executor.execute("contact.lookup", {"id": 4827, "name": None})
    assert r.data["id"] == 4827
