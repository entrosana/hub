"""FastAPI routes for scheduling."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_tenant_id
from app.scheduling import repository, service
from app.scheduling.schemas import ScheduleIn, ScheduleOut

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


@router.get("/", response_model=list[ScheduleOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=ScheduleOut, status_code=201)
async def create(
    payload: ScheduleIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_schedule(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
    )
    await db.commit()
    return obj
