"""FastAPI routes for identity."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity import repository, service
from app.identity.schemas import UserIn, UserOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/", response_model=list[UserOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=UserOut, status_code=201)
async def create(
    payload: UserIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_user(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
