"""FastAPI routes for admin."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import repository, service
from app.admin.models import Person
from app.admin.schemas import (
    PersonIn,
    PersonOut,
    ProviderCredentialIn,
    ProviderCredentialName,
    ProviderCredentialSetOut,
)
from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id
from app.providers import credentials

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


@router.get("/provider-credentials", response_model=list[ProviderCredentialName])
async def list_provider_credentials(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    names = await credentials.list_tenant_credential_names(db, tenant_id)
    return [
        ProviderCredentialName(provider_name=provider_name, setting_name=setting_name)
        for provider_name, setting_name in names
    ]


@router.put("/provider-credentials", response_model=ProviderCredentialSetOut)
async def set_provider_credential(
    payload: ProviderCredentialIn,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    _credential, rotated = await service.set_provider_credential(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        provider_name=payload.provider_name,
        setting_name=payload.setting_name,
        value=payload.value,
    )
    await db.commit()
    return ProviderCredentialSetOut(
        provider_name=payload.provider_name,
        setting_name=payload.setting_name,
        rotated=rotated,
    )


@router.delete(
    "/provider-credentials/{provider_name}/{setting_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_provider_credential(
    provider_name: str,
    setting_name: str,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await service.revoke_provider_credential(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        provider_name=provider_name,
        setting_name=setting_name,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credential not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
