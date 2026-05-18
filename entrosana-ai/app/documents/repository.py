"""DB access for documents.  Tenant-scoped reads + writes."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document


async def list_all(db: AsyncSession, tenant_id: str, limit: int = 50) -> list[Document]:
    q = select(Document).where(Document.tenant_id == tenant_id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def create(db: AsyncSession, tenant_id: str, **data) -> Document:
    obj = Document(tenant_id=tenant_id, **data)
    db.add(obj)
    await db.flush()
    return obj
