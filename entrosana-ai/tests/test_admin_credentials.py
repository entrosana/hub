"""Admin API tests for encrypted tenant provider credentials."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select

from app.audit.models import AuditEvent
from app.identity import service
from app.providers.models import TenantProviderCredential

PREFIX = "/api/v1"


async def _user_token(
    db,
    client,
    *,
    role: str = "admin",
    email: str | None = None,
) -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    email = email or f"{uuid.uuid4()}@example.com"
    password = secrets.token_urlsafe(24)
    await service.create_user(
        db,
        tenant_id=tenant_id,
        actor_id="setup",
        name="Admin",
        email=email,
        password=password,
        role=role,
    )
    await db.commit()
    response = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": email, "password": password},
    )
    return tenant_id, response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_set_creates_and_audits_without_secret(db, client):
    tenant_id, token = await _user_token(db, client)
    value = secrets.token_urlsafe(24)

    response = await client.put(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token),
        json={"provider_name": "cashctrl", "setting_name": "api_key", "value": value},
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "cashctrl",
        "setting_name": "api_key",
        "rotated": False,
    }
    event = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action == "admin.provider_credential.set",
                )
            )
        )
        .scalars()
        .one()
    )
    assert value not in response.text
    assert value not in str(event.before_state)
    assert value not in str(event.after_state)


async def test_rotate_updates_one_row_and_audits_rotation(db, client):
    tenant_id, token = await _user_token(db, client)
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)
    endpoint = f"{PREFIX}/admin/provider-credentials"
    payload = {"provider_name": "cashctrl", "setting_name": "api_key"}

    await client.put(endpoint, headers=_auth(token), json={**payload, "value": first})
    response = await client.put(endpoint, headers=_auth(token), json={**payload, "value": second})

    assert response.status_code == 200
    assert response.json()["rotated"] is True
    rows = (
        (
            await db.execute(
                select(TenantProviderCredential).where(
                    TenantProviderCredential.tenant_id == tenant_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    events = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action == "admin.provider_credential.set",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [event.after_state["rotated"] for event in events] == [False, True]
    assert all(first not in str(event.after_state) for event in events)
    assert all(second not in str(event.after_state) for event in events)


async def test_list_returns_names_only(db, client):
    _tenant_id, token = await _user_token(db, client)
    value = secrets.token_urlsafe(24)
    await client.put(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token),
        json={"provider_name": "cashctrl", "setting_name": "api_key", "value": value},
    )

    response = await client.get(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert response.json() == [{"provider_name": "cashctrl", "setting_name": "api_key"}]
    assert "value" not in response.text
    assert value not in response.text


async def test_delete_revokes_and_returns_404_when_absent(db, client):
    tenant_id, token = await _user_token(db, client)
    value = secrets.token_urlsafe(24)
    endpoint = f"{PREFIX}/admin/provider-credentials/cashctrl/api_key"
    await client.put(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token),
        json={"provider_name": "cashctrl", "setting_name": "api_key", "value": value},
    )

    response = await client.delete(endpoint, headers=_auth(token))
    assert response.status_code == 204
    assert response.content == b""
    assert (await client.delete(endpoint, headers=_auth(token))).status_code == 404
    event = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action == "admin.provider_credential.revoke",
                )
            )
        )
        .scalars()
        .one()
    )
    assert event.before_state["revoked"] is False
    assert event.after_state["revoked"] is True
    assert value not in str(event.before_state)
    assert value not in str(event.after_state)


async def test_credentials_are_tenant_isolated(db, client):
    tenant_one, token_one = await _user_token(db, client)
    _tenant_two, token_two = await _user_token(db, client)
    value = secrets.token_urlsafe(24)
    await client.put(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token_one),
        json={"provider_name": "cashctrl", "setting_name": "api_key", "value": value},
    )

    assert (
        await client.get(
            f"{PREFIX}/admin/provider-credentials",
            headers=_auth(token_two),
        )
    ).json() == []
    assert (
        await client.delete(
            f"{PREFIX}/admin/provider-credentials/cashctrl/api_key",
            headers=_auth(token_two),
        )
    ).status_code == 404
    assert (
        await db.execute(
            select(TenantProviderCredential).where(TenantProviderCredential.tenant_id == tenant_one)
        )
    ).scalar_one()


async def test_non_admin_is_rejected(db, client):
    _tenant_id, token = await _user_token(db, client, role="member")
    response = await client.get(
        f"{PREFIX}/admin/provider-credentials",
        headers=_auth(token),
    )
    assert response.status_code == 403
