"""DB access for taxes.

Generic CRUD lives in `app.core.crud`. Add tax-specific queries
(by period, by kind, overdue) here.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxes.models import Filing


async def list_by_year(db: AsyncSession, tenant_id: UUID, year: int) -> list[Filing]:
    q = (
        select(Filing)
        .where(Filing.tenant_id == tenant_id, Filing.period_year == year)
        .order_by(Filing.period_month.asc().nullsfirst(), Filing.kind.asc())
    )
    result = await db.execute(q)
    return list(result.scalars())
