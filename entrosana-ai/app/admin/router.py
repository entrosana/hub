"""FastAPI routes for admin."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository, service
from app.admin.models import Person
from app.admin.schemas import PersonIn, PersonOut
from app.core.crud import list_for_tenant
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/persons", response_model=list[PersonOut])
async def list_persons(
    kind: str | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if kind:
        return await repository.list_by_kind(db, tenant_id, kind, limit=limit)
    return await list_for_tenant(db, Person, tenant_id, limit=limit)


@router.post("/persons", response_model=PersonOut, status_code=201)
async def create_person(
    payload: PersonIn,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    person = await service.create_person(
        db,
        tenant_id=tenant_id,
        actor_id="system",
        name=payload.name,
        kind=payload.kind,
        email=payload.email,
    )
    await db.commit()
    return person
