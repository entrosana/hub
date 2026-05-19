"""FastAPI routes for taxes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_tenant_id
from app.taxes import repository, service
from app.taxes.schemas import FilingIn, FilingOut

router = APIRouter(prefix="/taxes", tags=["taxes"])


@router.get("/", response_model=list[FilingOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=FilingOut, status_code=201)
async def create(
    payload: FilingIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_filing(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
    )
    await db.commit()
    return obj
