"""DB access for billing.  Tenant-scoped reads + writes."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Invoice


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Invoice]:
    q = select(Invoice).where(Invoice.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Invoice:
    obj = Invoice(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
