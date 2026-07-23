"""DB access for identity.

Generic CRUD lives in `app.core.crud` (list_for_tenant, create_for_tenant,
get_for_tenant). Add identity-specific queries (lookup by email, role joins)
to this file as the domain grows.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User


async def find_by_email(db: AsyncSession, tenant_id: UUID, email: str) -> User | None:
    q = select(User).where(User.tenant_id == tenant_id, User.email == email)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def find_by_email_global(db: AsyncSession, email: str) -> User | None:
    """Look up a user by email across all tenants — used at LOGIN, before a
    tenant context exists. Email is the global login identifier; a global unique
    constraint on it is expected (see migration follow-up). `limit(1)` keeps the
    lookup deterministic even if that constraint is not yet enforced.
    """
    q = select(User).where(User.email == email).order_by(User.created_at.asc()).limit(1)
    result = await db.execute(q)
    return result.scalar_one_or_none()
