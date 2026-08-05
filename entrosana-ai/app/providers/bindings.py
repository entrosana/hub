"""DB-backed tenant-to-provider binding storage."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.errors import UnknownProviderError
from app.providers.models import TenantProviderBinding
from app.providers.registry import get_registry


async def get_tenant_binding(db: AsyncSession, tenant_id: UUID | str) -> str | None:
    """Return the active provider name for a tenant, if explicitly configured."""
    result = await db.execute(
        select(TenantProviderBinding.provider_name).where(
            TenantProviderBinding.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def set_tenant_binding(
    db: AsyncSession, tenant_id: UUID | str, provider_name: str
) -> TenantProviderBinding:
    """Validate and upsert a tenant's active provider binding."""
    if provider_name not in get_registry().providers:
        raise UnknownProviderError(provider_name)

    result = await db.execute(
        select(TenantProviderBinding).where(TenantProviderBinding.tenant_id == tenant_id)
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        binding = TenantProviderBinding(
            tenant_id=tenant_id,
            provider_name=provider_name,
            version=1,
        )
        db.add(binding)
    else:
        binding.provider_name = provider_name
        binding.version += 1
    await db.flush()
    return binding


async def delete_tenant_binding(db: AsyncSession, tenant_id: UUID | str) -> str | None:
    """Delete and return a tenant's explicit provider binding."""
    result = await db.execute(
        select(TenantProviderBinding).where(TenantProviderBinding.tenant_id == tenant_id)
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        return None
    provider_name = binding.provider_name
    await db.execute(delete(TenantProviderBinding).where(TenantProviderBinding.id == binding.id))
    await db.flush()
    return provider_name
