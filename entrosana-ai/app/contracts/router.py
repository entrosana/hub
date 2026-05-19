"""FastAPI routes for contracts."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import repository, service
from app.contracts.schemas import ContractIn, ContractOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/", response_model=list[ContractOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=ContractOut, status_code=201)
async def create(
    payload: ContractIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_contract(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
    )
    await db.commit()
    return obj
