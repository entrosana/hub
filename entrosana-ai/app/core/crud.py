"""Shared tenant-scoped CRUD helpers.

Every module's repository.py uses these helpers so the per-domain code stays
focused on what's actually domain-specific. Tenant isolation is enforced
here in exactly one place.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import TenantBase


async def list_for_tenant[T: TenantBase](
    db: AsyncSession,
    model: type[T],
    tenant_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[T]:
    q = (
        select(model)
        .where(model.tenant_id == tenant_id)
        .order_by(model.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())


async def create_for_tenant[T: TenantBase](
    db: AsyncSession,
    model: type[T],
    tenant_id: UUID,
    **fields,
) -> T:
    obj = model(tenant_id=tenant_id, **fields)
    db.add(obj)
    await db.flush()
    return obj


async def get_for_tenant[T: TenantBase](
    db: AsyncSession,
    model: type[T],
    tenant_id: UUID,
    obj_id: UUID,
) -> T | None:
    q = select(model).where(model.tenant_id == tenant_id, model.id == obj_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()
