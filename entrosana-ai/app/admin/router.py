"""FastAPI routes for admin."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository, service
from app.admin.models import Person
from app.admin.schemas import PersonIn, PersonOut, ProviderBindingIn, ProviderBindingOut
from app.audit import service as audit
from app.core.config import settings
from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id
from app.providers.bindings import (
    delete_tenant_binding,
    get_tenant_binding,
    set_tenant_binding,
)

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
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    person = await service.create_person(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        name=payload.name,
        kind=payload.kind,
        email=payload.email,
    )
    await db.commit()
    return person


@router.get(
    "/tenants/{tenant_id}/provider-binding",
    response_model=ProviderBindingOut,
)
async def get_provider_binding(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    provider = await get_tenant_binding(db, tenant_id)
    if provider is not None:
        source = "db"
    else:
        configured = settings.accounting_provider_bindings or {}
        provider = configured.get(str(tenant_id))
        source = "settings" if provider is not None else "default"
        if provider is None:
            provider = settings.default_accounting_provider
    return {"tenant_id": tenant_id, "provider": provider, "source": source}


@router.put(
    "/tenants/{tenant_id}/provider-binding",
    response_model=ProviderBindingOut,
)
async def set_provider_binding(
    tenant_id: UUID,
    payload: ProviderBindingIn,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    old_provider = await get_tenant_binding(db, tenant_id)
    binding = await set_tenant_binding(db, tenant_id, payload.provider)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="config.provider_binding.set",
        target_type="config.provider_binding",
        target_id=str(tenant_id),
        before={"provider": old_provider},
        after={"provider": binding.provider_name},
    )
    await db.commit()
    return {"tenant_id": tenant_id, "provider": binding.provider_name, "source": "db"}


@router.delete(
    "/tenants/{tenant_id}/provider-binding",
    response_model=ProviderBindingOut,
)
async def remove_provider_binding(
    tenant_id: UUID,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    old_provider = await delete_tenant_binding(db, tenant_id)
    if old_provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="binding not found")
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="config.provider_binding.delete",
        target_type="config.provider_binding",
        target_id=str(tenant_id),
        before={"provider": old_provider},
    )
    await db.commit()
    return {"tenant_id": tenant_id, "provider": old_provider, "source": "db"}
