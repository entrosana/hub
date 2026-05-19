"""Business logic for scheduling. All mutations route through audit.record()."""
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.scheduling.models import Schedule


async def create_schedule(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    room: str | None = None,
) -> Schedule:
    schedule = await create_for_tenant(
        db, Schedule, tenant_id,
        title=title, starts_at=starts_at, ends_at=ends_at, room=room,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="scheduling.schedule.create",
        target_type="schedule",
        target_id=str(schedule.id),
        after={
            "title": title,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "room": room,
        },
    )
    return schedule
