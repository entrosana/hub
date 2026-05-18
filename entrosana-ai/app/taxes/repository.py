"""DB access for taxes.  Tenant-scoped reads + writes."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxes.models import Filing


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Filing]:
    q = select(Filing).where(Filing.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Filing:
    obj = Filing(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
