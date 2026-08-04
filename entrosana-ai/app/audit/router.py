"""Audit query endpoints. Read-only — recording happens via service module."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventOut, ChainCheckpointResult, ChainVerificationResult
from app.audit.service import checkpoint_chain, verify_chain
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEventOut])
async def list_events(
    limit: int = 50,
    before_seq: int | None = None,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.seq.desc())
        .limit(min(limit, 200))
    )
    if before_seq is not None:
        q = q.where(AuditEvent.seq < before_seq)
    result = await db.execute(q)
    return list(result.scalars())


@router.post("/verify-chain", response_model=ChainVerificationResult)
async def verify_chain_route(
    full: bool = False,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    ok, n, first_bad = await verify_chain(db, tenant_id, full=full)
    return ChainVerificationResult(
        ok=ok,
        events_checked=n,
        first_bad_event_id=first_bad,
    )


@router.post("/checkpoint", response_model=ChainCheckpointResult)
async def checkpoint_chain_route(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    seq = await checkpoint_chain(db, tenant_id)
    await db.commit()
    return ChainCheckpointResult(seq=seq)
