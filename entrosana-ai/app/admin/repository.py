"""DB access for admin.  Tenant-scoped reads + writes."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Person


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Person]:
    q = select(Person).where(Person.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Person:
    obj = Person(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
