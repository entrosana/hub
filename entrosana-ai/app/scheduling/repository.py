"""DB access for scheduling.

Generic CRUD lives in `app.core.crud`. Add date-window queries
(today's classes, conflicts, substitute candidates) here.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduling.models import Schedule


async def list_in_window(
    db: AsyncSession, tenant_id: UUID, start: datetime, end: datetime
) -> list[Schedule]:
    q = (
        select(Schedule)
        .where(
            Schedule.tenant_id == tenant_id,
            Schedule.starts_at < end,
            Schedule.ends_at > start,
        )
        .order_by(Schedule.starts_at.asc())
    )
    result = await db.execute(q)
    return list(result.scalars())
