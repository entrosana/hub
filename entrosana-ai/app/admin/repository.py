"""DB access for admin.

Generic CRUD lives in `app.core.crud`. Add admin-specific queries
(filter by kind, parent-of-student joins) here as needed.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Person


async def list_by_kind(
    db: AsyncSession, tenant_id: UUID, kind: str, *, limit: int = 50
) -> list[Person]:
    q = (
        select(Person)
        .where(Person.tenant_id == tenant_id, Person.kind == kind)
        .order_by(Person.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())
