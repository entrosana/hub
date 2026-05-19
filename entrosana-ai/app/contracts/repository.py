"""DB access for contracts.

Generic CRUD lives in `app.core.crud`. Add contract-specific queries
(awaiting signature, expiring soon, by template version) here.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import Contract


async def list_awaiting_signature(
    db: AsyncSession, tenant_id: UUID, *, limit: int = 50
) -> list[Contract]:
    q = (
        select(Contract)
        .where(Contract.tenant_id == tenant_id, Contract.status == "sent")
        .order_by(Contract.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())
