"""Audit-chain HMAC verification.  Foundational — the DLM doctrine depends on this.

Two layers of test:

1. **Pure-crypto property tests** (no DB) — chain links, tamper detection,
   canonical serialisation.  Fast.
2. **End-to-end roundtrip tests** (in-memory SQLite) — call `record()` to
   sign and persist events, then `verify_chain()` to re-derive and check.
   This is what catches `_build_payload` drift between the signing path and
   the verification path (the timestamp-mismatch bug, etc.).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.audit import service as audit
from app.audit.models import AuditEvent
from app.audit.service import _canonical, _sign
from app.core.database import Base

GENESIS = "GENESIS"


def _build_chain(payloads: list[dict]) -> list[tuple[str, str]]:
    """Return [(prev_hmac, hmac), ...] for the chain of given payloads."""
    chain: list[tuple[str, str]] = []
    prev = GENESIS
    for p in payloads:
        sig = _sign(prev, p)
        chain.append((prev, sig))
        prev = sig
    return chain


# ── chain construction ─────────────────────────────────────────────────


def test_chain_links_each_event_to_previous():
    payloads = [
        {"action": "create", "v": 1},
        {"action": "update", "v": 2},
        {"action": "delete", "v": 3},
    ]
    chain = _build_chain(payloads)
    assert chain[0][0] == GENESIS
    assert chain[1][0] == chain[0][1]
    assert chain[2][0] == chain[1][1]


def test_each_event_has_distinct_signature():
    payloads = [{"action": f"a{i}"} for i in range(5)]
    sigs = [s for _, s in _build_chain(payloads)]
    assert len(set(sigs)) == 5


# ── tamper detection ───────────────────────────────────────────────────


def test_tampering_with_payload_breaks_signature():
    """If a stored event's payload is altered, recomputing its HMAC
    over the new payload yields a different value than what was recorded."""
    payloads = [
        {"action": "create", "v": 1},
        {"action": "update", "v": 2},
        {"action": "delete", "v": 3},
    ]
    chain = _build_chain(payloads)

    tampered_payload = dict(payloads[1], v=9999)
    recomputed = _sign(chain[1][0], tampered_payload)

    assert recomputed != chain[1][1], "Tampering with payload must produce a different HMAC"


def test_tampering_with_prev_hmac_breaks_signature():
    """A forged event claiming a different prev_hmac yields a different signature."""
    payloads = [{"action": "a"}, {"action": "b"}, {"action": "c"}]
    chain = _build_chain(payloads)

    forged_prev = "0" * 64
    forged_sig = _sign(forged_prev, payloads[2])

    assert forged_sig != chain[2][1]
    assert forged_prev != chain[2][0]


def test_genesis_chain_starts_from_literal_string():
    """First event's prev_hmac MUST be the literal string 'GENESIS' — auditors look for this."""
    chain = _build_chain([{"action": "first"}])
    assert chain[0][0] == "GENESIS"


# ── canonical serialisation ────────────────────────────────────────────


def test_canonical_is_order_independent():
    a = _canonical({"z": 1, "a": 2, "m": 3})
    b = _canonical({"a": 2, "m": 3, "z": 1})
    assert a == b


def test_canonical_distinguishes_values():
    assert _canonical({"v": 1}) != _canonical({"v": 2})


def test_canonical_distinguishes_int_vs_str():
    """1 and '1' canonicalise to different bytes — JSON typing matters."""
    assert _canonical({"v": 1}) != _canonical({"v": "1"})


def test_canonical_is_compact():
    """No whitespace padding — bytes are stable across formatters."""
    assert _canonical({"a": 1, "b": 2}) == b'{"a":1,"b":2}'


# ── end-to-end DB roundtrip (in-memory SQLite) ──────────────────────────


@pytest.fixture
async def db():
    """Per-test in-memory SQLite with all audit tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


async def test_record_then_verify_roundtrip(db):
    """record() signs an event; verify_chain() re-derives the signature.

    This is the regression test for the bug where `record()` signed
    `datetime.now()` but stored a different microsecond-later `created_at`,
    causing every verification to fail.
    """
    await audit.record(
        db,
        tenant_id="t1",
        actor_id="alice",
        action="entry.create",
        target_type="entry",
        target_id="1",
        after={"name": "test"},
    )
    await audit.record(
        db,
        tenant_id="t1",
        actor_id="alice",
        action="entry.update",
        target_type="entry",
        target_id="1",
        before={"name": "test"},
        after={"name": "updated"},
    )
    await audit.record(
        db,
        tenant_id="t1",
        actor_id="bob",
        action="entry.delete",
        target_type="entry",
        target_id="1",
        before={"name": "updated"},
    )
    ok, n = await audit.verify_chain(db, "t1")
    assert ok is True, "verify_chain must return True for an untampered chain"
    assert n == 3, "should have checked all three events"


async def test_chain_isolated_per_tenant(db):
    """Tenant A's chain is independent of tenant B's — both start from GENESIS."""
    await audit.record(
        db, tenant_id="A", actor_id="x", action="e.create", target_type="e", target_id="1"
    )
    await audit.record(
        db, tenant_id="B", actor_id="y", action="e.create", target_type="e", target_id="1"
    )
    await audit.record(
        db, tenant_id="A", actor_id="x", action="e.update", target_type="e", target_id="1"
    )
    ok_a, n_a = await audit.verify_chain(db, "A")
    ok_b, n_b = await audit.verify_chain(db, "B")
    assert (ok_a, n_a) == (True, 2)
    assert (ok_b, n_b) == (True, 1)


async def test_verify_chain_catches_tampered_after_state(db):
    """Mutating after_state on a persisted row makes verification fail at that row."""
    e1 = await audit.record(
        db,
        tenant_id="t2",
        actor_id="alice",
        action="entry.create",
        target_type="entry",
        target_id="1",
        after={"name": "test"},
    )
    e2 = await audit.record(
        db,
        tenant_id="t2",
        actor_id="alice",
        action="entry.update",
        target_type="entry",
        target_id="1",
        before={"name": "test"},
        after={"name": "updated"},
    )

    # Tamper: change e1's after_state directly in the DB session
    e1.after_state = {"name": "tampered"}
    await db.flush()

    ok, bad_id = await audit.verify_chain(db, "t2")
    assert ok is False
    assert bad_id == e1.id, "verifier should flag e1 as the first bad event"
    # e2's stored hmac is still valid for e2's own payload, but its prev_hmac
    # binds it to the ORIGINAL e1.hmac, so the chain is functionally broken.
    assert e2.prev_hmac == e1.hmac


async def test_verify_chain_catches_tampered_hmac(db):
    """Replacing a stored hmac directly makes verify_chain fail at that row."""
    e1 = await audit.record(
        db,
        tenant_id="t3",
        actor_id="alice",
        action="entry.create",
        target_type="entry",
        target_id="1",
    )
    await audit.record(
        db,
        tenant_id="t3",
        actor_id="alice",
        action="entry.update",
        target_type="entry",
        target_id="1",
    )
    e1.hmac = "0" * 64
    await db.flush()
    ok, bad_id = await audit.verify_chain(db, "t3")
    assert ok is False
    assert bad_id == e1.id


async def test_genesis_persists_to_db_as_literal_string(db):
    """The first event of any tenant has prev_hmac = 'GENESIS' on disk."""
    e1 = await audit.record(
        db, tenant_id="new-tenant", actor_id="x", action="e.create", target_type="e", target_id="1"
    )
    assert e1.prev_hmac == "GENESIS"


async def test_empty_chain_verifies_as_zero_events(db):
    """A tenant with no events has a verifiable (empty) chain."""
    ok, n = await audit.verify_chain(db, "tenant-with-no-events")
    assert ok is True
    assert n == 0


async def test_record_uses_consistent_timestamp(db):
    """The `ts` signed and the `created_at` stored must be the same instant.

    Regression test for the bug where `record()` signed `datetime.utcnow()`
    at one microsecond and SQLAlchemy's column default produced a different
    `created_at` a moment later — verify_chain() then failed on every event.
    """
    e = await audit.record(
        db, tenant_id="ts-check", actor_id="x", action="e.create", target_type="e", target_id="1"
    )
    ok, n = await audit.verify_chain(db, "ts-check")
    assert ok is True
    assert n == 1
    # Cross-check: the row's created_at, when isoformatted, must reproduce the
    # signed bytes byte-for-byte.
    payload = audit._build_payload(
        tenant_id=e.tenant_id,
        actor_id=e.actor_id,
        action=e.action,
        target_type=e.target_type,
        target_id=e.target_id,
        before=e.before_state,
        after=e.after_state,
        reasoning=e.reasoning,
        ts_iso=e.created_at.isoformat(),
    )
    assert audit._sign("GENESIS", payload) == e.hmac


# Use also the AuditEvent import so the linter doesn't complain.
_ = AuditEvent
