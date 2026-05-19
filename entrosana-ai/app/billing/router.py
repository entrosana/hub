"""FastAPI routes for billing."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import repository, service
from app.billing.models import Invoice
from app.billing.schemas import InvoiceIn, InvoiceOut
from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    overdue_as_of: date | None = None,
    family_id: str | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if overdue_as_of:
        return await repository.list_overdue(db, tenant_id, overdue_as_of, limit=limit)
    if family_id:
        return await repository.list_for_family(db, tenant_id, family_id)
    return await list_for_tenant(db, Invoice, tenant_id, limit=limit)


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
async def issue_invoice(
    payload: InvoiceIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    invoice = await service.issue_invoice(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        number=payload.number,
        family_id=payload.family_id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        issued_on=payload.issued_on,
        due_on=payload.due_on,
    )
    await db.commit()
    return invoice
