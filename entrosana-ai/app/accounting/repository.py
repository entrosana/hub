"""DB access for accounting.

Generic CRUD lives in `app.core.crud`. Add domain-specific queries
here (filter by status, sum by period, reconcile against CashCtrl).
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Entry


async def list_by_status(
    db: AsyncSession, tenant_id: UUID, status: str, *, limit: int = 50
) -> list[Entry]:
    q = (
        select(Entry)
        .where(Entry.tenant_id == tenant_id, Entry.status == status)
        .order_by(Entry.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())
