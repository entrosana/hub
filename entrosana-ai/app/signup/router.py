"""FastAPI routes for signup."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id
from app.signup import service
from app.signup.models import Application
from app.signup.schemas import ApplicationIn, ApplicationOut

router = APIRouter(prefix="/signup", tags=["signup"])


@router.get("/applications", response_model=list[ApplicationOut])
async def list_applications(
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await list_for_tenant(db, Application, tenant_id, limit=limit)


@router.post("/applications", response_model=ApplicationOut, status_code=201)
async def submit_application(
    payload: ApplicationIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    application = await service.submit_application(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        student_name=payload.student_name,
        parent_name=payload.parent_name,
        parent_email=payload.parent_email,
    )
    await db.commit()
    return application
