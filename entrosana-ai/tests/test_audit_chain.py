"""Audit-chain HMAC verification — the DLM doctrine depends on this.

The chain links every signed mutation per tenant. If a row's `hmac` is
altered, verification must fail at that exact row.
"""
from uuid import uuid4

from app.audit import service as audit
from app.audit.models import AuditEvent


async def test_chain_verifies_when_intact(db):
    tenant = uuid4()
    for i in range(3):
        await audit.record(
            db,
            tenant_id=tenant,
            actor_id="alice",
            action="test.event",
            target_type="thing",
            target_id=str(i),
            after={"i": i},
        )
    await db.flush()

    ok, n, bad = await audit.verify_chain(db, tenant)
    assert ok is True
    assert n == 3
    assert bad is None


async def test_chain_breaks_on_tampered_hmac(db):
    tenant = uuid4()
    events = []
    for i in range(3):
        e = await audit.record(
            db,
            tenant_id=tenant,
            actor_id="alice",
            action="test.event",
            target_type="thing",
            target_id=str(i),
            after={"i": i},
        )
        events.append(e)
    await db.flush()

    # Tamper with the middle event's hmac.
    events[1].hmac = "deadbeef" * 8
    await db.flush()

    ok, _, first_bad = await audit.verify_chain(db, tenant)
    assert ok is False
    assert first_bad == events[1].id


async def test_chain_is_tenant_isolated(db):
    tenant_a, tenant_b = uuid4(), uuid4()
    await audit.record(
        db,
        tenant_id=tenant_a,
        actor_id="a",
        action="x",
        target_type="t",
        target_id="1",
    )
    await audit.record(
        db,
        tenant_id=tenant_b,
        actor_id="b",
        action="x",
        target_type="t",
        target_id="2",
    )
    await db.flush()

    ok_a, n_a, _ = await audit.verify_chain(db, tenant_a)
    ok_b, n_b, _ = await audit.verify_chain(db, tenant_b)
    assert ok_a is True and n_a == 1
    assert ok_b is True and n_b == 1


async def test_genesis_anchor_links_first_event(db):
    """The very first event in a tenant's chain must have prev_hmac=GENESIS."""
    tenant = uuid4()
    e = await audit.record(
        db,
        tenant_id=tenant,
        actor_id="alice",
        action="first",
        target_type="t",
        target_id="1",
    )
    assert e.prev_hmac == audit.GENESIS
    assert isinstance(e, AuditEvent)
