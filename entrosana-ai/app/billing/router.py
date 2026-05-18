"""FastAPI routes for billing."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import repository, service
from app.billing.schemas import InvoiceIn, InvoiceOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/", response_model=list[InvoiceOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=InvoiceOut, status_code=201)
async def create(
    payload: InvoiceIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_invoice(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
