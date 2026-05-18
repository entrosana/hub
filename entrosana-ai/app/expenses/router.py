"""FastAPI routes for expenses."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.expenses import repository, service
from app.expenses.schemas import ExpenseIn, ExpenseOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/", response_model=list[ExpenseOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=ExpenseOut, status_code=201)
async def create(
    payload: ExpenseIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_expense(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
