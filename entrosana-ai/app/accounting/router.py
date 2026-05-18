"""FastAPI routes for accounting."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import repository, service
from app.accounting.schemas import EntryIn, EntryOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("/", response_model=list[EntryOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=EntryOut, status_code=201)
async def create(
    payload: EntryIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_entry(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
