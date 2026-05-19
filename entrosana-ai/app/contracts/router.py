"""FastAPI routes for contracts."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import repository, service
from app.contracts.models import Contract
from app.contracts.schemas import ContractIn, ContractOut
from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/", response_model=list[ContractOut])
async def list_contracts(
    awaiting_signature: bool = False,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if awaiting_signature:
        return await repository.list_awaiting_signature(db, tenant_id, limit=limit)
    return await list_for_tenant(db, Contract, tenant_id, limit=limit)


@router.post("/", response_model=ContractOut, status_code=201)
async def draft_contract(
    payload: ContractIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    contract = await service.draft_contract(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        title=payload.title,
        template_version=payload.template_version,
    )
    await db.commit()
    return contract
