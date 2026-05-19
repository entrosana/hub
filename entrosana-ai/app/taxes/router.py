"""FastAPI routes for taxes."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id
from app.taxes import repository, service
from app.taxes.models import Filing
from app.taxes.schemas import FilingIn, FilingOut

router = APIRouter(prefix="/taxes", tags=["taxes"])


@router.get("/filings", response_model=list[FilingOut])
async def list_filings(
    year: int | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if year is not None:
        return await repository.list_by_year(db, tenant_id, year)
    return await list_for_tenant(db, Filing, tenant_id, limit=limit)


@router.post("/filings", response_model=FilingOut, status_code=201)
async def draft_filing(
    payload: FilingIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    filing = await service.draft_filing(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        kind=payload.kind,
        period_year=payload.period_year,
        period_month=payload.period_month,
    )
    await db.commit()
    return filing
