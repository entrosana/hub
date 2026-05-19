"""FastAPI routes for addresses."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses import repository, service
from app.addresses.schemas import AddressIn, AddressOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("/", response_model=list[AddressOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=AddressOut, status_code=201)
async def create(
    payload: AddressIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_address(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
    )
    await db.commit()
    return obj
