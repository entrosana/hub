"""DB access for billing.

Generic CRUD lives in `app.core.crud`. Add invoice-specific queries
(overdue, per-family open balance, reconciliation against CashCtrl) here.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Invoice


async def list_overdue(
    db: AsyncSession, tenant_id: UUID, as_of: date, *, limit: int = 50
) -> list[Invoice]:
    q = (
        select(Invoice)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == "open",
            Invoice.due_on < as_of,
        )
        .order_by(Invoice.due_on.asc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())


async def list_for_family(db: AsyncSession, tenant_id: UUID, family_id: str) -> list[Invoice]:
    q = (
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id, Invoice.family_id == family_id)
        .order_by(Invoice.issued_on.desc())
    )
    result = await db.execute(q)
    return list(result.scalars())
