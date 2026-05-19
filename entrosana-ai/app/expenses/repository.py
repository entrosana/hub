"""DB access for expenses.

Generic CRUD lives in `app.core.crud`. Add expense-specific queries
(pending approvals, period-bound aggregations) here.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.expenses.models import Expense


async def list_pending(
    db: AsyncSession, tenant_id: UUID, *, limit: int = 50
) -> list[Expense]:
    q = (
        select(Expense)
        .where(Expense.tenant_id == tenant_id, Expense.status == "submitted")
        .order_by(Expense.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())
