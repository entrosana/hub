"""DB access for addresses.  Tenant-scoped reads + writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Address]:
    q = select(Address).where(Address.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Address:
    obj = Address(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
