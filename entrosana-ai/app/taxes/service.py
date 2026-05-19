"""Business logic for taxes. All mutations route through audit.record()."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.taxes.models import Filing


async def draft_filing(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    kind: str,
    period_year: int,
    period_month: int | None = None,
) -> Filing:
    filing = await create_for_tenant(
        db, Filing, tenant_id,
        kind=kind, period_year=period_year, period_month=period_month,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="taxes.filing.draft",
        target_type="filing",
        target_id=str(filing.id),
        after={
            "kind": kind,
            "period_year": period_year,
            "period_month": period_month,
        },
    )
    return filing
