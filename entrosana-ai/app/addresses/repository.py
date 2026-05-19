"""DB access for addresses.

Generic CRUD lives in `app.core.crud`. Add address-specific queries
(by postcode, dedupe lookup) here.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address


async def find_by_postcode(
    db: AsyncSession, tenant_id: UUID, postcode: str
) -> list[Address]:
    q = (
        select(Address)
        .where(Address.tenant_id == tenant_id, Address.postcode == postcode)
        .order_by(Address.city.asc(), Address.line1.asc())
    )
    result = await db.execute(q)
    return list(result.scalars())
