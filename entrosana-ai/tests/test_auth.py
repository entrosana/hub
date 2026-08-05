"""Auth layer tests — prove the audit C1/C2 cross-tenant breach is closed.

Covers: unauthenticated access is rejected, tenant is derived from the verified
token (a spoofed X-Tenant-Id header is ignored), and forged/expired/wrong-type
tokens are rejected.
"""

import uuid

import jwt
import pytest

from app.core.config import settings
from app.identity import service

PREFIX = "/api/v1"
pytestmark = pytest.mark.anyio


async def _make_user(db, *, tenant_id, email, password, role="member"):
    u = await service.create_user(
        db, tenant_id=tenant_id, actor_id="test-setup",
        name="Test", email=email, password=password, role=role,
    )
    await db.commit()
    return u


async def _login(client, email, password):
    return await client.post(f"{PREFIX}/auth/login", json={"email": email, "password": password})


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


async def test_protected_endpoint_requires_auth(client):
    r = await client.get(f"{PREFIX}/identity/users")
    assert r.status_code == 401


async def test_login_then_access(db, client):
    t = uuid.uuid4()
    await _make_user(db, tenant_id=t, email="a@example.com", password="correcthorsestaple")
    r = await _login(client, "a@example.com", "correcthorsestaple")
    assert r.status_code == 200
    tok = r.json()["access_token"]
    r2 = await client.get(f"{PREFIX}/identity/users", headers=_auth(tok))
    assert r2.status_code == 200
    assert [u["email"] for u in r2.json()] == ["a@example.com"]


async def test_wrong_password_rejected(db, client):
    await _make_user(db, tenant_id=uuid.uuid4(), email="b@example.com", password="rightpassword12")
    r = await _login(client, "b@example.com", "wrongpassword12")
    assert r.status_code == 401


async def test_unknown_email_rejected(client):
    r = await _login(client, "nobody@example.com", "whateverpass123")
    assert r.status_code == 401


async def test_tenant_derived_from_token_not_header(db, client):
    """C1/C2: a token for tenant A cannot read tenant B — and a spoofed
    X-Tenant-Id header does NOT override the token's tenant."""
    ta, tb = uuid.uuid4(), uuid.uuid4()
    await _make_user(db, tenant_id=ta, email="alice@example.com", password="alicepass12345")
    await _make_user(db, tenant_id=tb, email="bob@example.com", password="bobpass1234567")
    tok = (await _login(client, "alice@example.com", "alicepass12345")).json()["access_token"]
    r = await client.get(
        f"{PREFIX}/identity/users",
        headers={**_auth(tok), "X-Tenant-Id": str(tb)},  # attacker tries to pivot to tenant B
    )
    assert r.status_code == 200
    assert {u["email"] for u in r.json()} == {"alice@example.com"}  # NOT bob


async def test_alg_none_token_rejected(client):
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "tid": str(uuid.uuid4()), "role": "admin",
         "type": "access", "iat": 0, "exp": 9999999999},
        "", algorithm="none",
    )
    r = await client.get(f"{PREFIX}/identity/users", headers=_auth(forged))
    assert r.status_code == 401


async def test_wrong_secret_token_rejected(client):
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "tid": str(uuid.uuid4()), "role": "admin",
         "type": "access", "iat": 0, "exp": 9999999999},
        "attacker-guessed-key", algorithm="HS256",
    )
    r = await client.get(f"{PREFIX}/identity/users", headers=_auth(forged))
    assert r.status_code == 401


async def test_refresh_token_not_accepted_as_access(db, client):
    await _make_user(db, tenant_id=uuid.uuid4(), email="c@example.com", password="password123456")
    refresh = (await _login(client, "c@example.com", "password123456")).json()["refresh_token"]
    r = await client.get(f"{PREFIX}/identity/users", headers=_auth(refresh))
    assert r.status_code == 401


async def test_expired_token_rejected(client):
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "tid": str(uuid.uuid4()), "role": "member",
         "type": "access", "iat": 0, "exp": 1},
        settings.secret_key, algorithm=settings.jwt_algorithm,
    )
    r = await client.get(f"{PREFIX}/identity/users", headers=_auth(expired))
    assert r.status_code == 401


async def test_me_returns_principal(db, client):
    t = uuid.uuid4()
    u = await _make_user(db, tenant_id=t, email="d@example.com", password="password123456", role="admin")
    tok = (await _login(client, "d@example.com", "password123456")).json()["access_token"]
    r = await client.get(f"{PREFIX}/auth/me", headers=_auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == str(t)
    assert body["user_id"] == str(u.id)
    assert body["role"] == "admin"


async def test_admin_route_requires_admin_role(db, client):
    t = uuid.uuid4()
    await _make_user(db, tenant_id=t, email="member@example.com", password="password123456", role="member")
    await _make_user(db, tenant_id=t, email="boss@example.com", password="password123456", role="admin")
    member_tok = (await _login(client, "member@example.com", "password123456")).json()["access_token"]
    admin_tok = (await _login(client, "boss@example.com", "password123456")).json()["access_token"]
    assert (await client.get(f"{PREFIX}/admin/persons", headers=_auth(member_tok))).status_code == 403
    assert (await client.get(f"{PREFIX}/admin/persons", headers=_auth(admin_tok))).status_code == 200


async def test_refresh_blocks_deactivated_user(db, client):
    """Adversarial finding: a deactivated user must not renew via refresh."""
    t = uuid.uuid4()
    u = await _make_user(db, tenant_id=t, email="revoke@example.com", password="password123456", role="admin")
    refresh = (await _login(client, "revoke@example.com", "password123456")).json()["refresh_token"]
    u.is_active = False
    await db.commit()
    r = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_refresh_reflects_role_revocation(db, client):
    """A demoted admin's refresh yields a member token — no frozen role."""
    t = uuid.uuid4()
    u = await _make_user(db, tenant_id=t, email="demote@example.com", password="password123456", role="admin")
    refresh = (await _login(client, "demote@example.com", "password123456")).json()["refresh_token"]
    u.role = "member"
    await db.commit()
    r = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_access = r.json()["access_token"]
    assert (await client.get(f"{PREFIX}/admin/persons", headers=_auth(new_access))).status_code == 403


async def test_actor_attribution_is_real_user(db, client):
    """H1: an authenticated create is attributed to the caller, not 'system'."""
    from sqlalchemy import select

    from app.audit.models import AuditEvent

    t = uuid.uuid4()
    caller = await _make_user(db, tenant_id=t, email="caller@example.com", password="password123456")
    tok = (await _login(client, "caller@example.com", "password123456")).json()["access_token"]
    r = await client.post(
        f"{PREFIX}/identity/users",
        headers=_auth(tok),
        json={"name": "New", "email": "new@example.com", "password": "anotherpassword12"},
    )
    assert r.status_code == 201
    rows = (
        await db.execute(select(AuditEvent).where(AuditEvent.action == "identity.user.create"))
    ).scalars().all()
    actors = {e.actor_id for e in rows}
    assert str(caller.id) in actors  # the API create is attributed to the caller
    assert "system" not in actors  # the hardcoded placeholder is gone from the request path
