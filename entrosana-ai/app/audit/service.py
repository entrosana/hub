"""Audit recording service -- the DLM signed-trail spine.

Every mutating operation in the system MUST call `audit.record(...)` before
returning to the client.  The HMAC chain ensures any tampering with history
breaks the chain.
"""
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.core.config import settings


def _canonical(payload: dict[str, Any]) -> bytes:
    """Stable JSON serialisation for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(prev_hmac: str, payload: dict) -> str:
    msg = prev_hmac.encode() + _canonical(payload)
    return hmac.new(settings.dlm_audit_hmac_key.encode(), msg, hashlib.sha256).hexdigest()


async def _last_hmac(session: AsyncSession, tenant_id: str) -> str:
    q = (
        select(AuditEvent.hmac)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.id.desc())
        .limit(1)
    )
    result = await session.execute(q)
    row = result.scalar_one_or_none()
    return row or "GENESIS"


async def record(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    before: dict | None = None,
    after: dict | None = None,
    reasoning: str | None = None,
) -> AuditEvent:
    """Append a signed audit event.  Returns the persisted event."""
    prev_hmac = await _last_hmac(session, tenant_id)
    payload = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "before": before or {},
        "after": after or {},
        "reasoning": reasoning,
        "ts": datetime.utcnow().isoformat(),
    }
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
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession, tenant_id: str) -> tuple[bool, int]:
    """Walk the chain for a tenant and verify every signature.  Returns (ok, n_events)."""
    q = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.id.asc())
    result = await session.execute(q)
    events = result.scalars().all()
    prev = "GENESIS"
    for e in events:
        payload = {
            "tenant_id": e.tenant_id,
            "actor_id": e.actor_id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "before": e.before_state,
            "after": e.after_state,
            "reasoning": e.reasoning,
            "ts": e.created_at.isoformat(),
        }
        expected = _sign(prev, payload)
        if expected != e.hmac:
            return False, e.id
        prev = e.hmac
    return True, len(events)
