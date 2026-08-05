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

from app.audit.models import (
    AuditChainCheckpoint,
    AuditChainHead,
    AuditEvent,
    AuditEventArchive,
    DLMInteraction,
)
from app.core import metrics
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
    q = select(AuditChainHead).where(AuditChainHead.tenant_id == tenant_id).with_for_update()
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
    metrics.observe_audit(action)
    return event


def _event_payload(event: AuditEvent | AuditEventArchive) -> dict:
    return _build_payload(
        seq=event.seq,
        tenant_id=event.tenant_id,
        actor_id=event.actor_id,
        action=event.action,
        target_type=event.target_type,
        target_id=event.target_id,
        before=event.before_state,
        after=event.after_state,
        reasoning=event.reasoning,
        ts_iso=event.created_at.replace(tzinfo=None).isoformat(),
    )


async def verify_chain(
    session: AsyncSession, tenant_id: UUID, *, full: bool = False
) -> tuple[bool, int, UUID | None]:
    """Verify the tenant's chain, using a checkpoint unless ``full`` is set.

    Returns (ok, n_events, first_bad_event_id). `first_bad_event_id` is set when a
    specific row fails (bad signature / broken link / gap / unknown key); for a
    structural failure with no single culprit (tail-truncation, missing anchor)
    it is None while ok is False.
    """
    keyring = _keyring()
    head = (
        await session.execute(select(AuditChainHead).where(AuditChainHead.tenant_id == tenant_id))
    ).scalar_one_or_none()
    checkpoint = (
        await session.execute(
            select(AuditChainCheckpoint).where(AuditChainCheckpoint.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()

    if full or checkpoint is None:
        archive_events = list(
            (
                await session.execute(
                    select(AuditEventArchive)
                    .where(AuditEventArchive.tenant_id == tenant_id)
                    .order_by(AuditEventArchive.seq.asc())
                )
            ).scalars()
        )
        hot_events = list(
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.tenant_id == tenant_id)
                    .order_by(AuditEvent.seq.asc())
                )
            ).scalars()
        )
        events: list[AuditEvent | AuditEventArchive] = [*archive_events, *hot_events]
        events.sort(key=lambda event: event.seq)
        prev = GENESIS
        expected_seq = 1
        n = len(events)
    else:
        events = list(
            (
                await session.execute(
                    select(AuditEvent)
                    .where(
                        AuditEvent.tenant_id == tenant_id,
                        AuditEvent.seq > checkpoint.seq,
                    )
                    .order_by(AuditEvent.seq.asc())
                )
            ).scalars()
        )
        prev = checkpoint.hmac
        expected_seq = checkpoint.seq + 1
        n = checkpoint.seq + len(events)

    last_seq = expected_seq - 1
    last_hmac = prev
    for event in events:
        if event.seq != expected_seq:  # gap or reorder
            return False, n, event.id
        if event.prev_hmac != prev:  # broken chain link
            return False, n, event.id
        key = keyring.get(event.key_id)
        if key is None:  # signed with an unknown/dropped key
            return False, n, event.id
        if _sign(prev, _event_payload(event), key) != event.hmac:
            return False, n, event.id
        prev = event.hmac
        last_seq = event.seq
        last_hmac = event.hmac
        expected_seq += 1

    if head is None:
        return (n == 0), n, None  # events present but no anchor = anchor removed
    if n != head.seq or last_seq != head.seq:
        return False, n, None
    if n > 0 and last_hmac != head.head_hmac:
        return False, n, None
    return True, n, None


async def checkpoint_chain(session: AsyncSession, tenant_id: UUID) -> int:
    """Persist a checkpoint only after the fast chain verification succeeds."""
    ok, _n, first_bad = await verify_chain(session, tenant_id)
    if not ok:
        raise ValueError(f"cannot checkpoint invalid audit chain (first bad event: {first_bad})")

    head = (
        await session.execute(select(AuditChainHead).where(AuditChainHead.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if head is None or head.seq == 0:
        return 0

    checkpoint = (
        await session.execute(
            select(AuditChainCheckpoint).where(AuditChainCheckpoint.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if checkpoint is None:
        checkpoint = AuditChainCheckpoint(
            tenant_id=tenant_id,
            seq=head.seq,
            hmac=head.head_hmac,
        )
        session.add(checkpoint)
    else:
        checkpoint.seq = head.seq
        checkpoint.hmac = head.head_hmac
    await session.flush()
    return checkpoint.seq


async def archive_checkpointed(session: AsyncSession, tenant_id: UUID) -> int:
    """Move events covered by the tenant's checkpoint to cold storage."""
    checkpoint = (
        await session.execute(
            select(AuditChainCheckpoint).where(AuditChainCheckpoint.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if checkpoint is None:
        raise ValueError("cannot archive audit events without a checkpoint")

    events = list(
        (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.seq <= checkpoint.seq,
                )
                .order_by(AuditEvent.seq.asc())
            )
        ).scalars()
    )
    for event in events:
        session.add(
            AuditEventArchive(
                id=event.id,
                tenant_id=event.tenant_id,
                seq=event.seq,
                actor_id=event.actor_id,
                action=event.action,
                target_type=event.target_type,
                target_id=event.target_id,
                before_state=event.before_state,
                after_state=event.after_state,
                reasoning=event.reasoning,
                prev_hmac=event.prev_hmac,
                hmac=event.hmac,
                key_id=event.key_id,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
        )
        await session.delete(event)
    await session.flush()
    return len(events)


async def record_dlm(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    input_payload: dict,
    runner_result: dict,
    audit_event_id: UUID | None = None,
) -> DLMInteraction:
    """Persist one signed DLM interaction row (audit M4 — this row was declared
    mandatory by runner.run's contract but never actually written).

    `runner_result` is exactly the dict returned by `app.dlm.runner.run`
    (output + model_version + prompt_version + retrieval_keys + token counts).
    `audit_event_id` links the interaction to the audit event it justified, when
    the call drove a recorded action. The row's hmac is a standalone signature of
    the pinned inputs/outputs (this is a supplementary log, not the append-only
    chain), signed with the current audit key.
    """
    output_payload = {
        "output": runner_result.get("output", ""),
        "tokens_in": runner_result.get("tokens_in"),
        "tokens_out": runner_result.get("tokens_out"),
    }
    retrieval_keys = sorted(runner_result.get("retrieval_keys", []))
    signed = {
        "tenant_id": str(tenant_id),
        "audit_event_id": str(audit_event_id) if audit_event_id else None,
        "model_version": runner_result.get("model_version", ""),
        "prompt_version": runner_result.get("prompt_version", ""),
        "temperature": settings.dlm_temperature,
        "input": input_payload,
        "output": output_payload,
        "retrieval_keys": retrieval_keys,
    }
    _key_id, key = _current_key()
    interaction = DLMInteraction(
        tenant_id=tenant_id,
        audit_event_id=audit_event_id,
        model_version=runner_result.get("model_version", ""),
        prompt_version=runner_result.get("prompt_version", ""),
        temperature=settings.dlm_temperature,
        input_payload=input_payload,
        output_payload=output_payload,
        retrieval_keys=retrieval_keys,
        hmac=_sign("", signed, key),  # standalone signature (not the chain)
    )
    session.add(interaction)
    await session.flush()
    return interaction
