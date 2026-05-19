"""FastAPI routes for identity."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id
from app.identity import service
from app.identity.models import User
from app.identity.schemas import UserIn, UserOut

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await list_for_tenant(db, User, tenant_id, limit=limit)


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    user = await service.create_user(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
        email=payload.email,
        password=payload.password,
    )
    await db.commit()
    return user
