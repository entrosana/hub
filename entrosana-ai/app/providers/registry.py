"""Provider registry + per-tenant resolution.

Loads every declarative spec once and answers two questions:
  * which provider does this tenant run on?  (``provider_for_tenant``)
  * give me its spec / an executor for it.   (``resolve`` / ``executor_for_tenant``)

Binding source today is settings (``accounting_provider_bindings`` with a
``default_accounting_provider`` fallback). The seam is deliberate: a DB-backed
per-tenant binding table drops in behind ``provider_for_tenant`` later without the
executor, specs, or dispatcher changing (ADR 0002).
"""

from __future__ import annotations

from uuid import UUID

from app.core.config import settings
from app.providers.errors import UnknownProviderError
from app.providers.executor import ProviderExecutor
from app.providers.spec import SPECS_DIR, ProviderSpec, load_all
from app.providers.transport import Transport


class ProviderRegistry:
    def __init__(self, specs: dict[str, ProviderSpec] | None = None) -> None:
        self._specs = specs if specs is not None else load_all(SPECS_DIR)

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

    def provider_for_tenant(self, tenant_id: UUID | str) -> str:
        """Name of the accounting provider bound to this tenant."""
        bindings = settings.accounting_provider_bindings or {}
        return bindings.get(str(tenant_id), settings.default_accounting_provider)

    def resolve(self, tenant_id: UUID | str) -> ProviderSpec:
        """Spec for the tenant's provider (raises UnknownProviderError if the
        bound/default provider has no spec — a config error, surfaced loudly)."""
        return self.get(self.provider_for_tenant(tenant_id))

    def credentials_for_tenant(self, tenant_id: UUID | str) -> dict[str, str]:
        """Tenant-scoped secret overrides ({settings_attr: value}); empty dict
        falls back to global settings (single-tenant / dev only — see config)."""
        return (settings.accounting_tenant_credentials or {}).get(str(tenant_id), {})

    def executor_for_tenant(self, tenant_id: UUID | str, transport: Transport) -> ProviderExecutor:
        return ProviderExecutor(
            self.resolve(tenant_id),
            transport,
            credential_overrides=self.credentials_for_tenant(tenant_id),
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
