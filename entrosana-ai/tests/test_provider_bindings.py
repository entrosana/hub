"""Tests for DB-backed tenant provider bindings and their admin surface."""

from __future__ import annotations

import secrets
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.core.config import settings
from app.identity import service as identity_service
from app.providers import bindings
from app.providers.credentials import get_tenant_credentials, set_tenant_credential
from app.providers.domains.accounting import FallbackBindingSource
from app.providers.errors import UnknownProviderError
from app.providers.fake import FakeCashCtrlTransport
from app.providers.registry import get_registry

pytestmark = pytest.mark.anyio


async def test_binding_repository_upserts_versions_and_deletes(db):
    tenant = uuid4()

    assert await bindings.get_tenant_binding(db, tenant) is None
    first = await bindings.set_tenant_binding(db, tenant, "cashctrl")
    assert first.provider_name == "cashctrl"
    assert first.version == 1
    assert await bindings.get_tenant_binding(db, tenant) == "cashctrl"

    second = await bindings.set_tenant_binding(db, tenant, "cashctrl")
    assert second.id == first.id
    assert second.provider_name == "cashctrl"
    assert second.version == 2

    assert await bindings.delete_tenant_binding(db, tenant) == "cashctrl"
    assert await bindings.get_tenant_binding(db, tenant) is None
    assert await bindings.delete_tenant_binding(db, tenant) is None


async def test_binding_repository_rejects_unknown_provider(db):
    with pytest.raises(UnknownProviderError):
        await bindings.set_tenant_binding(db, uuid4(), "not-a-provider")


async def test_binding_source_prefers_db_then_settings_then_default(db, monkeypatch):
    tenant = uuid4()
    source = FallbackBindingSource()
    monkeypatch.setattr(settings, "accounting_provider_bindings", {str(tenant): "bexio"})
    monkeypatch.setattr(settings, "default_accounting_provider", "cashctrl")

    assert await source.provider_for_tenant(tenant, session=db) == "bexio"
    assert await source.provider_for_tenant(uuid4(), session=db) == "cashctrl"
    assert await source.provider_for_tenant(tenant) == "bexio"

    await bindings.set_tenant_binding(db, tenant, "cashctrl")
    assert await source.provider_for_tenant(tenant, session=db) == "cashctrl"


async def test_registry_and_credentials_use_db_binding(db):
    tenant = uuid4()
    await bindings.set_tenant_binding(db, tenant, "cashctrl")
    key = secrets.token_urlsafe(16)
    await set_tenant_credential(db, tenant, "cashctrl", "cashctrl_api_key", key)
    await db.commit()

    registry = get_registry()
    assert (await registry.resolve(tenant, session=db)).name == "cashctrl"
    executor = await registry.executor_for_tenant(tenant, FakeCashCtrlTransport(), session=db)
    assert executor.spec.name == "cashctrl"
    assert await get_tenant_credentials(db, tenant) == {"cashctrl_api_key": key}


async def _admin_token(db, client, tenant_id):
    password = secrets.token_urlsafe(24)
    user = await identity_service.create_user(
        db,
        tenant_id=tenant_id,
        actor_id="test-setup",
        name="Admin",
        email=f"{uuid4()}@example.com",
        password=password,
        role="admin",
    )
    await db.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_admin_binding_api_audits_and_reports_sources(db, client, monkeypatch):
    admin_tenant = uuid4()
    target_tenant = uuid4()
    headers = await _admin_token(db, client, admin_tenant)
    monkeypatch.setattr(settings, "default_accounting_provider", "cashctrl")

    initial = await client.get(
        f"/api/v1/admin/tenants/{target_tenant}/provider-binding",
        headers=headers,
    )
    assert initial.status_code == 200
    assert initial.json() == {
        "tenant_id": str(target_tenant),
        "provider": "cashctrl",
        "source": "default",
    }

    monkeypatch.setattr(
        settings,
        "accounting_provider_bindings",
        {str(target_tenant): "bexio"},
    )
    configured = await client.get(
        f"/api/v1/admin/tenants/{target_tenant}/provider-binding",
        headers=headers,
    )
    assert configured.json()["source"] == "settings"
    assert configured.json()["provider"] == "bexio"

    updated = await client.put(
        f"/api/v1/admin/tenants/{target_tenant}/provider-binding",
        headers=headers,
        json={"provider": "cashctrl"},
    )
    assert updated.status_code == 200
    assert updated.json()["source"] == "db"

    event = (
        await db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == target_tenant,
                AuditEvent.action == "config.provider_binding.set",
            )
            .order_by(AuditEvent.created_at.desc())
        )
    ).scalar_one()
    assert event.before_state == {"provider": None}
    assert event.after_state == {"provider": "cashctrl"}

    removed = await client.delete(
        f"/api/v1/admin/tenants/{target_tenant}/provider-binding",
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["provider"] == "cashctrl"
    assert (
        await client.delete(
            f"/api/v1/admin/tenants/{target_tenant}/provider-binding",
            headers=headers,
        )
    ).status_code == 404

    deleted_event = (
        await db.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == target_tenant,
                AuditEvent.action == "config.provider_binding.delete",
            )
        )
    ).scalar_one()
    assert deleted_event.before_state == {"provider": "cashctrl"}


async def test_admin_binding_api_rejects_unknown_provider(db, client):
    headers = await _admin_token(db, client, uuid4())
    response = await client.put(
        f"/api/v1/admin/tenants/{uuid4()}/provider-binding",
        headers=headers,
        json={"provider": "invalid"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "unknown provider: invalid"
