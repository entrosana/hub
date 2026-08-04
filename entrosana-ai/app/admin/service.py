"""Business logic for admin. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Person
from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.providers import credentials
from app.providers.models import TenantProviderCredential


async def create_person(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    name: str,
    kind: str,
    email: str | None = None,
) -> Person:
    person = await create_for_tenant(db, Person, tenant_id, name=name, kind=kind, email=email)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="admin.person.create",
        target_type="person",
        target_id=str(person.id),
        after={"name": name, "kind": kind, "email": email},
    )
    return person


def _credential_payload(
    *,
    tenant_id: UUID,
    provider_name: str,
    setting_name: str,
    rotated: bool,
    revoked: bool = False,
) -> dict[str, str | bool]:
    return {
        "tenant_id": str(tenant_id),
        "provider_name": provider_name,
        "setting_name": setting_name,
        "rotated": rotated,
        "revoked": revoked,
    }


async def set_provider_credential(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    provider_name: str,
    setting_name: str,
    value: str,
) -> tuple[TenantProviderCredential, bool]:
    existing = (
        await db.execute(
            select(TenantProviderCredential).where(
                TenantProviderCredential.tenant_id == tenant_id,
                TenantProviderCredential.provider_name == provider_name,
                TenantProviderCredential.setting_name == setting_name,
            )
        )
    ).scalar_one_or_none()
    rotated = existing is not None
    credential = await credentials.set_tenant_credential(
        db, tenant_id, provider_name, setting_name, value
    )
    payload = _credential_payload(
        tenant_id=tenant_id,
        provider_name=provider_name,
        setting_name=setting_name,
        rotated=rotated,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="admin.provider_credential.set",
        target_type="provider_credential",
        target_id=f"{provider_name}/{setting_name}",
        before=payload,
        after=payload,
    )
    return credential, rotated


async def revoke_provider_credential(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    provider_name: str,
    setting_name: str,
) -> bool:
    payload = _credential_payload(
        tenant_id=tenant_id,
        provider_name=provider_name,
        setting_name=setting_name,
        rotated=False,
    )
    deleted = await credentials.delete_tenant_credential(db, tenant_id, provider_name, setting_name)
    if not deleted:
        return False
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="admin.provider_credential.revoke",
        target_type="provider_credential",
        target_id=f"{provider_name}/{setting_name}",
        before=payload,
        after={**payload, "revoked": True},
    )
    return True
