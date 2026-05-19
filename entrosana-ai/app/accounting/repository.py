"""DB access for accounting.  Tenant-scoped reads + writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Entry


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Entry]:
    q = select(Entry).where(Entry.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Entry:
    obj = Entry(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
