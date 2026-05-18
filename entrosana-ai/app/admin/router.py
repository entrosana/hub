"""FastAPI routes for admin."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository, service
from app.admin.schemas import PersonIn, PersonOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/", response_model=list[PersonOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=PersonOut, status_code=201)
async def create(
    payload: PersonIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_person(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
