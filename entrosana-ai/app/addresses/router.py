"""FastAPI routes for addresses."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses import repository, service
from app.addresses.models import Address
from app.addresses.schemas import AddressIn, AddressOut
from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("/", response_model=list[AddressOut])
async def list_addresses(
    postcode: str | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if postcode:
        return await repository.find_by_postcode(db, tenant_id, postcode)
    return await list_for_tenant(db, Address, tenant_id, limit=limit)


@router.post("/", response_model=AddressOut, status_code=201)
async def register_address(
    payload: AddressIn,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    address = await service.register_address(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        line1=payload.line1,
        line2=payload.line2,
        postcode=payload.postcode,
        city=payload.city,
        country=payload.country,
    )
    await db.commit()
    return address
