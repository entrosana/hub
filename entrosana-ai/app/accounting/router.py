"""FastAPI routes for accounting."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import repository, service
from app.accounting.models import Entry
from app.accounting.schemas import EntryIn, EntryOut
from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("/entries", response_model=list[EntryOut])
async def list_entries(
    status: str | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if status:
        return await repository.list_by_status(db, tenant_id, status, limit=limit)
    return await list_for_tenant(db, Entry, tenant_id, limit=limit)


@router.post("/entries", response_model=EntryOut, status_code=201)
async def propose_entry(
    payload: EntryIn,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    entry = await service.propose_entry(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        description=payload.description,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
    )
    await db.commit()
    return entry
