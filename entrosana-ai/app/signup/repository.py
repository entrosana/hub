"""DB access for signup.  Tenant-scoped reads + writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.signup.models import Application


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Application]:
    q = select(Application).where(Application.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Application:
    obj = Application(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
