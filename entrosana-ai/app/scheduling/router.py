"""FastAPI routes for scheduling."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id
from app.scheduling import repository, service
from app.scheduling.models import Schedule
from app.scheduling.schemas import ScheduleIn, ScheduleOut

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if start and end:
        return await repository.list_in_window(db, tenant_id, start, end)
    return await list_for_tenant(db, Schedule, tenant_id, limit=limit)


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    payload: ScheduleIn,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    schedule = await service.create_schedule(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        title=payload.title,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        room=payload.room,
    )
    await db.commit()
    return schedule
