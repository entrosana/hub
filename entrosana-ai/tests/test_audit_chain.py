"""Audit-chain HMAC verification — the DLM doctrine depends on this.

The chain links every signed mutation per tenant. If a row's `hmac` is
altered, verification must fail at that exact row.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import service as audit
from app.audit.models import AuditEvent, AuditEventArchive
from app.identity import service as identity_service


async def _record_n(db, tenant, n):
    events = []
    for i in range(n):
        events.append(
            await audit.record(
                db,
                tenant_id=tenant,
                actor_id="a",
                action="test.event",
                target_type="thing",
                target_id=str(i),
                after={"i": i},
            )
        )
    await db.flush()
    return events


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


async def test_tail_truncation_detected(db):
    """H2: deleting rows from the END of the chain must fail verification."""
    tenant = uuid4()
    await _record_n(db, tenant, 3)
    ok, n, _ = await audit.verify_chain(db, tenant)
    assert ok is True and n == 3

    last = (
        await db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant)
            .order_by(AuditEvent.seq.desc())
            .limit(1)
        )
    ).scalar_one()
    await db.delete(last)
    await db.flush()

    ok2, n2, _ = await audit.verify_chain(db, tenant)
    assert ok2 is False  # anchor still says seq=3; only 2 rows survive → detected
    assert n2 == 2


async def test_middle_deletion_detected(db):
    """M2: a gap in the sequence is detected (chain no longer 1..N)."""
    tenant = uuid4()
    events = await _record_n(db, tenant, 3)
    await db.delete(events[1])  # remove seq=2
    await db.flush()

    ok, _, _ = await audit.verify_chain(db, tenant)
    assert ok is False


async def test_unique_seq_prevents_fork(db):
    """H3 backstop: two events cannot claim the same (tenant, seq) slot."""
    tenant = uuid4()
    await _record_n(db, tenant, 1)
    dup = AuditEvent(
        tenant_id=tenant,
        seq=1,
        actor_id="x",
        action="e",
        target_type="t",
        target_id="dup",
        before_state={},
        after_state={},
        prev_hmac=audit.GENESIS,
        hmac="0" * 16,
        key_id="k1",
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_unknown_key_id_fails_verify(db):
    """M3: a row signed with a key not in the keyring cannot be verified."""
    tenant = uuid4()
    (e,) = await _record_n(db, tenant, 1)
    e.key_id = "not-in-keyring"
    await db.flush()
    ok, _, bad = await audit.verify_chain(db, tenant)
    assert ok is False and bad == e.id


async def test_key_rotation_keeps_old_rows_verifiable(db, monkeypatch):
    """M3: after rotating the signing key, rows signed by the retired key still
    verify as long as the retired key stays in the keyring."""
    tenant = uuid4()
    old = b"retired-audit-key-abcdefghijklmnop"
    new = b"current-audit-key-qrstuvwxyz012345"

    monkeypatch.setattr(audit, "_current_key", lambda: ("old", old))
    monkeypatch.setattr(audit, "_keyring", lambda: {"old": old})
    await audit.record(
        db, tenant_id=tenant, actor_id="a", action="e", target_type="t", target_id="1"
    )
    await db.flush()

    # rotate: sign new rows with "new", but keep "old" in the keyring
    monkeypatch.setattr(audit, "_current_key", lambda: ("new", new))
    monkeypatch.setattr(audit, "_keyring", lambda: {"new": new, "old": old})
    await audit.record(
        db, tenant_id=tenant, actor_id="a", action="e", target_type="t", target_id="2"
    )
    await db.flush()

    ok, n, _ = await audit.verify_chain(db, tenant)
    assert ok is True and n == 2


async def test_checkpoint_fast_and_full_verification_match(db):
    tenant = uuid4()
    await _record_n(db, tenant, 3)

    checkpoint_seq = await audit.checkpoint_chain(db, tenant)

    assert checkpoint_seq == 3
    assert (await audit.verify_chain(db, tenant)) == (True, 3, None)
    assert (await audit.verify_chain(db, tenant, full=True)) == (True, 3, None)


async def test_archive_checkpointed_preserves_verification_and_count(db):
    tenant = uuid4()
    await _record_n(db, tenant, 4)
    await audit.checkpoint_chain(db, tenant)

    archived = await audit.archive_checkpointed(db, tenant)
    await db.flush()

    hot = (
        (await db.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant))).scalars().all()
    )
    cold = (
        (await db.execute(select(AuditEventArchive).where(AuditEventArchive.tenant_id == tenant)))
        .scalars()
        .all()
    )
    assert archived == 4
    assert hot == []
    assert [event.seq for event in cold] == [1, 2, 3, 4]
    assert (await audit.verify_chain(db, tenant)) == (True, 4, None)
    assert (await audit.verify_chain(db, tenant, full=True)) == (True, 4, None)


async def test_fast_path_trusts_checkpoint_but_full_detects_archived_tampering(db):
    tenant = uuid4()
    await _record_n(db, tenant, 3)
    await audit.checkpoint_chain(db, tenant)
    await audit.archive_checkpointed(db, tenant)

    archived = (
        await db.execute(
            select(AuditEventArchive).where(
                AuditEventArchive.tenant_id == tenant,
                AuditEventArchive.seq == 2,
            )
        )
    ).scalar_one()
    archived.hmac = "deadbeef" * 8
    await db.flush()

    assert (await audit.verify_chain(db, tenant)) == (True, 3, None)
    ok, n, first_bad = await audit.verify_chain(db, tenant, full=True)
    assert ok is False
    assert n == 3
    assert first_bad == archived.id


async def test_fast_path_detects_hot_tampering_after_checkpoint(db):
    tenant = uuid4()
    await _record_n(db, tenant, 3)
    await audit.checkpoint_chain(db, tenant)
    event = await audit.record(
        db,
        tenant_id=tenant,
        actor_id="a",
        action="after.checkpoint",
        target_type="thing",
        target_id="4",
    )
    event.hmac = "deadbeef" * 8
    await db.flush()

    ok, n, first_bad = await audit.verify_chain(db, tenant)
    assert ok is False
    assert n == 4
    assert first_bad == event.id


async def test_fast_path_detects_tail_truncation_after_checkpoint(db):
    tenant = uuid4()
    await _record_n(db, tenant, 3)
    await audit.checkpoint_chain(db, tenant)
    event = await audit.record(
        db,
        tenant_id=tenant,
        actor_id="a",
        action="after.checkpoint",
        target_type="thing",
        target_id="4",
    )
    await db.delete(event)
    await db.flush()

    ok, n, first_bad = await audit.verify_chain(db, tenant)
    assert ok is False
    assert n == 3
    assert first_bad is None


async def test_fast_path_detects_gap_after_checkpoint(db):
    tenant = uuid4()
    await _record_n(db, tenant, 3)
    await audit.checkpoint_chain(db, tenant)
    first = await audit.record(
        db,
        tenant_id=tenant,
        actor_id="a",
        action="after.checkpoint",
        target_type="thing",
        target_id="4",
    )
    second = await audit.record(
        db,
        tenant_id=tenant,
        actor_id="a",
        action="after.checkpoint",
        target_type="thing",
        target_id="5",
    )
    await db.delete(first)
    await db.flush()

    ok, n, first_bad = await audit.verify_chain(db, tenant)
    assert ok is False
    assert n == 4
    assert first_bad == second.id


async def test_audit_events_cursor_pagination(db, client):
    tenant = uuid4()
    email = f"{uuid4()}@example.com"
    password = uuid4().hex
    await identity_service.create_user(
        db,
        tenant_id=tenant,
        actor_id="setup",
        name="Auditor",
        email=email,
        password=password,
    )
    await db.commit()
    token = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await _record_n(db, tenant, 5)
    await db.commit()

    first_page = await client.get(
        "/api/v1/audit/events",
        params={"limit": 2},
        headers=headers,
    )
    second_page = await client.get(
        "/api/v1/audit/events",
        params={"limit": 2, "before_seq": 6},
        headers=headers,
    )
    assert [event["target_id"] for event in first_page.json()] == ["4", "3"]
    assert [event["target_id"] for event in second_page.json()] == ["3", "2"]
