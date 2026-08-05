"""Provider registry + per-tenant resolution.

Loads every declarative spec once and answers two questions:
  * which provider does this tenant run on?  (``provider_for_tenant``)
  * give me its spec / an executor for it.   (``resolve`` / ``executor_for_tenant``)

Which tenant runs on which provider is answered by a :class:`BindingSource`, not
by the registry itself. The active domain pack installs one (the accounting pack
reads it from settings); a DB-backed binding table drops in behind the same
protocol later without the executor, specs, or dispatcher changing (ADR 0002).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.errors import UnknownProviderError
from app.providers.executor import ProviderExecutor
from app.providers.spec import SPECS_DIR, ProviderSpec, load_all
from app.providers.transport import Transport


@runtime_checkable
class BindingSource(Protocol):
    """How a deployment answers 'which provider, and with which secrets?'."""

    def provider_for_tenant(self, tenant_id: UUID | str) -> str: ...

    async def credentials_for_tenant(
        self, tenant_id: UUID | str, session: AsyncSession | None = None
    ) -> dict[str, str]: ...


_binding_source: BindingSource | None = None


def set_binding_source(source: BindingSource) -> None:
    """Install the active binding source (called by the domain pack on import)."""

    global _binding_source
    _binding_source = source


def get_binding_source() -> BindingSource:
    if _binding_source is None:
        raise UnknownProviderError(
            "no binding source installed — import a domain pack (app.providers.domains.*)"
        )
    return _binding_source


class ProviderRegistry:
    def __init__(
        self,
        specs: dict[str, ProviderSpec] | None = None,
        binding: BindingSource | None = None,
    ) -> None:
        self._specs = specs if specs is not None else load_all(SPECS_DIR)
        self._binding = binding

    @property
    def providers(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> ProviderSpec:
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownProviderError(name)
        return spec

    def capabilities(self, name: str) -> set[str]:
        return self.get(name).capabilities

    def __init_binding__(self) -> BindingSource:  # pragma: no cover - trivial
        return self._binding or get_binding_source()

    def provider_for_tenant(self, tenant_id: UUID | str) -> str:
        """Name of the provider bound to this tenant."""
        return self.__init_binding__().provider_for_tenant(tenant_id)

    def resolve(self, tenant_id: UUID | str) -> ProviderSpec:
        """Spec for the tenant's provider (raises UnknownProviderError if the
        bound/default provider has no spec — a config error, surfaced loudly)."""
        return self.get(self.provider_for_tenant(tenant_id))

    async def credentials_for_tenant(
        self, tenant_id: UUID | str, session: AsyncSession | None = None
    ) -> dict[str, str]:
        """Tenant-scoped secret overrides ({settings_attr: value}); empty dict
        falls back to global settings (single-tenant / dev only — see config)."""
        return await self.__init_binding__().credentials_for_tenant(tenant_id, session)

    async def executor_for_tenant(
        self, tenant_id: UUID | str, transport: Transport, session: AsyncSession | None = None
    ) -> ProviderExecutor:
        return ProviderExecutor(
            self.resolve(tenant_id),
            transport,
            credential_overrides=await self.credentials_for_tenant(tenant_id, session),
        )


# ── process-wide singleton (lazy; specs load on first use) ─────────────────

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_registry() -> None:
    """Clear the singleton — tests only."""
    global _registry
    _registry = None
