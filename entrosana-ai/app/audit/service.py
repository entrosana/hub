"""Audit recording service — the signed-trail spine.

Every mutating operation MUST call `record(...)` before returning to the client.
The chain is tamper-evident:

* each event carries a monotonic per-tenant `seq` that is part of the signed
  payload, so reordering or gaps are detected;
* the per-tenant head (`AuditChainHead`) anchors the highest seq + its hmac, so
  deleting rows from the tail is detected (the prefix stays self-consistent but
  no longer matches the anchor);
* appends serialize on the head row (`SELECT ... FOR UPDATE`) and are backstopped
  by `UNIQUE(tenant_id, seq)`, so concurrent writers cannot fork the chain;
* each row records the `key_id` that signed it, so keys can be rotated while old
  rows stay verifiable via the keyring.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditChainHead, AuditEvent
from app.core.config import settings

GENESIS = "GENESIS"


def _keyring() -> dict[str, bytes]:
    """key_id -> key bytes. Extend with retired keys (id: key) to verify old
    rows after a rotation; the current key is always present for signing."""
    return {settings.dlm_audit_hmac_key_id: settings.dlm_audit_hmac_key.encode()}


def _current_key() -> tuple[str, bytes]:
    return settings.dlm_audit_hmac_key_id, settings.dlm_audit_hmac_key.encode()


def _canonical(payload: dict[str, Any]) -> bytes:
    """Stable JSON serialisation for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(prev_hmac: str, payload: dict, key: bytes) -> str:
    msg = prev_hmac.encode() + _canonical(payload)
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _build_payload(
    *,
    seq: int,
    tenant_id: UUID,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    before: dict | None,
    after: dict | None,
    reasoning: str | None,
    ts_iso: str,
) -> dict:
    """Canonical signed payload — shared by record() and verify_chain().

    `seq` binds each event to its position in the chain. `ts_iso` is the
    naive-UTC ISO string; verify_chain() strips tzinfo on read so SQLite (drops
    tz) and Postgres (keeps tz) both reproduce the same bytes.
    """
    return {
        "seq": seq,
        "tenant_id": str(tenant_id),
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "before": before or {},
        "after": after or {},
        "reasoning": reasoning,
        "ts": ts_iso,
    }


async def _lock_head(session: AsyncSession, tenant_id: UUID) -> AuditChainHead:
    """Fetch-and-lock the tenant's head row (create at GENESIS if absent).

    `with_for_update()` serialises concurrent appends per tenant on Postgres
    (it is a no-op on SQLite, where the single connection already serialises;
    the UNIQUE(tenant_id, seq) constraint is the cross-dialect backstop).
    """
    q = (
        select(AuditChainHead)
        .where(AuditChainHead.tenant_id == tenant_id)
        .with_for_update()
    )
    head = (await session.execute(q)).scalar_one_or_none()
    if head is None:
        head = AuditChainHead(tenant_id=tenant_id, seq=0, head_hmac=GENESIS)
        session.add(head)
        await session.flush()
    return head


async def record(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    before: dict | None = None,
    after: dict | None = None,
    reasoning: str | None = None,
) -> AuditEvent:
    """Append a signed audit event. Returns the persisted event."""
    head = await _lock_head(session, tenant_id)
    prev_hmac = head.head_hmac
    seq = head.seq + 1

    ts = datetime.now(UTC)
    ts_iso = ts.replace(tzinfo=None).isoformat()
    payload = _build_payload(
        seq=seq,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        reasoning=reasoning,
        ts_iso=ts_iso,
    )
    key_id, key = _current_key()
    sig = _sign(prev_hmac, payload, key)

    event = AuditEvent(
        tenant_id=tenant_id,
        seq=seq,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_state=before or {},
        after_state=after or {},
        reasoning=reasoning,
        prev_hmac=prev_hmac,
        hmac=sig,
        key_id=key_id,
        created_at=ts,
    )
    session.add(event)
    # advance the anchor in the same transaction
    head.seq = seq
    head.head_hmac = sig
    await session.flush()
    return event


async def verify_chain(session: AsyncSession, tenant_id: UUID) -> tuple[bool, int, UUID | None]:
    """Verify a tenant's chain end to end.

    Returns (ok, n_events, first_bad_event_id). `first_bad_event_id` is set when a
    specific row fails (bad signature / broken link / gap / unknown key); for a
    structural failure with no single culprit (tail-truncation, missing anchor)
    it is None while ok is False.
    """
    keyring = _keyring()
    events = list(
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == tenant_id)
                .order_by(AuditEvent.seq.asc())
            )
        ).scalars()
    )
    head = (
        await session.execute(
            select(AuditChainHead).where(AuditChainHead.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()

    prev = GENESIS
    for i, e in enumerate(events, start=1):
        if e.seq != i:  # gap or reorder
            return False, len(events), e.id
        if e.prev_hmac != prev:  # broken chain link
            return False, len(events), e.id
        key = keyring.get(e.key_id)
        if key is None:  # signed with an unknown/dropped key
            return False, len(events), e.id
        payload = _build_payload(
            seq=e.seq,
            tenant_id=e.tenant_id,
            actor_id=e.actor_id,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            before=e.before_state,
            after=e.after_state,
            reasoning=e.reasoning,
            ts_iso=e.created_at.replace(tzinfo=None).isoformat(),
        )
        if _sign(prev, payload, key) != e.hmac:  # tampered payload/signature
            return False, len(events), e.id
        prev = e.hmac

    n = len(events)
    # Anchor check — this is what makes tail-truncation detectable.
    if head is None:
        return (n == 0), n, None  # events present but no anchor = anchor removed
    if n != head.seq:  # rows deleted from the tail (or count mismatch)
        return False, n, None
    if n > 0 and prev != head.head_hmac:  # final hmac must match the anchor
        return False, n, None
    return True, n, None
