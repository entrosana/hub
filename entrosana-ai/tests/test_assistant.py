"""Assistant endpoint + dispatcher tests.

Proves the whole product loop through the API: prose → canonical op → tenant's
provider (offline fake) → signed audit chain + DLMInteraction row → response.
Also: auth gating, and that mutations are previewed (never auto-applied).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent, DLMInteraction
from app.core.auth import Principal
from app.core.dependencies import get_accounting_transport
from app.dlm.dispatch import dispatch_query
from app.dlm.gateway import DLMGateway
from app.dlm.intent import ToolCall
from app.identity import service
from app.main import app
from app.providers.fake import FakeCashCtrlTransport

PREFIX = "/api/v1"


@pytest.fixture(autouse=True)
async def _override_transport(client):
    """Route the executor over the offline fake (depends on `client` so it is set
    after the client's dependency overrides, and cleaned up by the client fixture)."""
    app.dependency_overrides[get_accounting_transport] = lambda: FakeCashCtrlTransport()
    yield


async def _user_token(db, client, *, email="u@example.com", pw="password123456", role="member"):
    t = uuid.uuid4()
    u = await service.create_user(
        db, tenant_id=t, actor_id="setup", name="U", email=email, password=pw, role=role
    )
    await db.commit()
    r = await client.post(f"{PREFIX}/auth/login", json={"email": email, "password": pw})
    return t, u, r.json()["access_token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def test_query_requires_auth(client):
    r = await client.post(f"{PREFIX}/assistant/query", json={"input": "contact 4827"})
    assert r.status_code == 401


async def test_query_executes_and_signs_audit(db, client):
    t, _u, tok = await _user_token(db, client)
    r = await client.post(
        f"{PREFIX}/assistant/query",
        headers=_auth(tok),
        json={"input": "pull May payments of Anna Müller from 01.05.2026 to 31.05.2026"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool"] == "journal.list"
    assert body["executed"] is True
    assert body["count"] == 2
    assert body["source"] == "cashctrl"
    assert [e["id"] for e in body["result"]] == ["JE-2026-0421", "JE-2026-0445"]

    # two-phase signed trail: a query.requested row committed BEFORE execution,
    # then one query.executed row + one DLMInteraction row for this tenant
    requested = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == t, AuditEvent.action == "query.requested"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(requested) == 1
    assert requested[0].after_state["provider"] == "cashctrl"
    assert requested[0].after_state["spec_version"]  # spec version pinned (replay)
    events = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == t, AuditEvent.action == "query.executed"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].after_state["result_count"] == 2
    assert events[0].after_state["spec_version"]
    dlm_rows = (
        (await db.execute(select(DLMInteraction).where(DLMInteraction.tenant_id == t)))
        .scalars()
        .all()
    )
    assert len(dlm_rows) == 1
    assert dlm_rows[0].audit_event_id == events[0].id
    assert dlm_rows[0].model_version == "mock-router"
    assert len(dlm_rows[0].hmac) == 64


async def test_query_journal_get(db, client):
    _t, _u, tok = await _user_token(db, client)
    r = await client.post(
        f"{PREFIX}/assistant/query",
        headers=_auth(tok),
        json={"input": "show me journal JE-2026-0445"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "journal.get"
    assert body["result"]["title"].startswith("Lehrmittel")


async def test_query_contact_lookup(db, client):
    _t, _u, tok = await _user_token(db, client)
    r = await client.post(
        f"{PREFIX}/assistant/query",
        headers=_auth(tok),
        json={"input": "contact 4827"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "contact.lookup"
    assert body["result"]["name"] == "Anna Müller"


async def test_audit_chain_verifies_after_query(db, client):
    from app.audit.service import verify_chain

    t, _u, tok = await _user_token(db, client)
    await client.post(
        f"{PREFIX}/assistant/query",
        headers=_auth(tok),
        json={"input": "contact 4827"},
    )
    ok, n, bad = await verify_chain(db, t)
    assert ok is True
    assert n >= 1
    assert bad is None


async def test_mutation_previews_with_signed_provenance_but_never_executes(db):
    """A mutation (journal.create) must NOT execute — but the PROPOSAL itself is
    signed provenance: one mutation.proposed audit row + one DLMInteraction row,
    and nothing else. The confirm leg is a separate, explicit call (ADR 0002)."""

    class _CreateRouter:
        async def route(self, _s: str) -> ToolCall:
            return ToolCall(
                "journal.create",
                {
                    "date": "2026-06-10",
                    "amount": "99.00",
                    "debit_account": 1100,
                    "credit_account": 3000,
                    "title": "Field trip",
                },
            )

    gw = DLMGateway(_CreateRouter())
    principal = Principal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="member")
    res = await dispatch_query(
        db,
        principal,
        "book a field trip expense",
        gateway=gw,
        transport=FakeCashCtrlTransport(),
    )
    assert res.kind == "mutation"
    assert res.executed is False
    assert res.result is None
    assert "journal.create" in res.summary

    # exactly ONE audit row — the signed proposal — and its linked DLM row;
    # no query.executed, nothing executed against the provider.
    events = (
        (await db.execute(select(AuditEvent).where(AuditEvent.tenant_id == principal.tenant_id)))
        .scalars()
        .all()
    )
    assert [e.action for e in events] == ["mutation.proposed"]
    assert events[0].after_state["args"]["amount"] == "99.00"
    dlm_rows = (
        (
            await db.execute(
                select(DLMInteraction).where(DLMInteraction.tenant_id == principal.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(dlm_rows) == 1
    assert dlm_rows[0].audit_event_id == events[0].id
