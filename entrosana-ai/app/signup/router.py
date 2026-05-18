"""FastAPI routes for signup."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.signup import repository, service
from app.signup.schemas import ApplicationIn, ApplicationOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/signup", tags=["signup"])


@router.get("/", response_model=list[ApplicationOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=ApplicationOut, status_code=201)
async def create(
    payload: ApplicationIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_application(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
