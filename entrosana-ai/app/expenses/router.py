"""FastAPI routes for expenses."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id
from app.expenses import repository, service
from app.expenses.models import Expense
from app.expenses.schemas import ExpenseIn, ExpenseOut

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/", response_model=list[ExpenseOut])
async def list_expenses(
    pending: bool = False,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if pending:
        return await repository.list_pending(db, tenant_id, limit=limit)
    return await list_for_tenant(db, Expense, tenant_id, limit=limit)


@router.post("/", response_model=ExpenseOut, status_code=201)
async def submit_expense(
    payload: ExpenseIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    expense = await service.submit_expense(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        description=payload.description,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        receipt_document_id=payload.receipt_document_id,
    )
    await db.commit()
    return expense
