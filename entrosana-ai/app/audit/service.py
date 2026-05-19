"""Audit recording service — the DLM signed-trail spine.

Every mutating operation in the system MUST call `audit.record(...)` before
returning to the client. The HMAC chain ensures any tampering with history
breaks the chain.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.core.config import settings

GENESIS = "GENESIS"


def _canonical(payload: dict[str, Any]) -> bytes:
    """Stable JSON serialisation for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(prev_hmac: str, payload: dict) -> str:
    msg = prev_hmac.encode() + _canonical(payload)
    return hmac.new(settings.dlm_audit_hmac_key.encode(), msg, hashlib.sha256).hexdigest()


def _build_payload(
    *,
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
    """Canonical payload shape — shared by record() and verify_chain().

    `ts_iso` is the naive-UTC ISO string that gets signed.  record() picks
    one moment and uses it for both the signed payload and the stored
    created_at; verify_chain() strips tzinfo on read so SQLite (drops tz)
    and Postgres (preserves tz) both produce the same bytes.
    """
    return {
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


async def _last_hmac(session: AsyncSession, tenant_id: UUID) -> str:
    q = (
        select(AuditEvent.hmac)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    result = await session.execute(q)
    row = result.scalar_one_or_none()
    return row or GENESIS


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
    """Append a signed audit event.  Returns the persisted event.

    The same ts is signed AND stored as created_at.  Without this invariant
    the signed bytes and the bytes verify_chain() recomputes would differ
    by microseconds and every verification would fail.
    """
    prev_hmac = await _last_hmac(session, tenant_id)
    ts = datetime.now(UTC)
    ts_iso = ts.replace(tzinfo=None).isoformat()
    payload = _build_payload(
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
    sig = _sign(prev_hmac, payload)
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_state=before or {},
        after_state=after or {},
        reasoning=reasoning,
        prev_hmac=prev_hmac,
        hmac=sig,
        created_at=ts,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession, tenant_id: UUID) -> tuple[bool, int, UUID | None]:
    """Walk the chain for a tenant and verify every signature.

    Returns (ok, n_events, first_bad_event_id).
    """
    q = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.asc())
    )
    result = await session.execute(q)
    events = result.scalars().all()
    prev = GENESIS
    for e in events:
        payload = _build_payload(
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
        expected = _sign(prev, payload)
        if expected != e.hmac:
            return False, len(events), e.id
        prev = e.hmac
    return True, len(events), None
