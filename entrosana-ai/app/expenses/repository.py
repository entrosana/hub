"""DB access for expenses.  Tenant-scoped reads + writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.expenses.models import Expense


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Expense]:
    q = select(Expense).where(Expense.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Expense:
    obj = Expense(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
