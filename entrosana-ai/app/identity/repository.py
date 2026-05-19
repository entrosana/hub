"""DB access for identity.

Generic CRUD lives in `app.core.crud` (list_for_tenant, create_for_tenant,
get_for_tenant). Add identity-specific queries (lookup by email, role joins)
to this file as the domain grows.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.identity.models import User


async def find_by_email(db: AsyncSession, tenant_id: UUID, email: str) -> User | None:
    q = select(User).where(User.tenant_id == tenant_id, User.email == email)
    result = await db.execute(q)
    return result.scalar_one_or_none()
