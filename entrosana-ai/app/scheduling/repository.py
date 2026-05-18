"""DB access for scheduling.  Tenant-scoped reads + writes."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduling.models import Schedule


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Schedule]:
    q = select(Schedule).where(Schedule.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Schedule:
    obj = Schedule(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
