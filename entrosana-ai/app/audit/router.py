"""Audit query endpoints.  Read-only -- recording happens via service module."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventOut, ChainVerificationResult
from app.audit.service import verify_chain
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEventOut])
async def list_events(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.id.desc())
        .limit(min(limit, 200))
    )
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/verify-chain", response_model=ChainVerificationResult)
async def verify_chain_route(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    ok, n = await verify_chain(db, tenant_id)
    return ChainVerificationResult(
        ok=ok,
        events_checked=n,
        first_bad_event_id=None if ok else n + 1,
    )
