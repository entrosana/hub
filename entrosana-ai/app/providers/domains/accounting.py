"""Accounting domain pack.

Everything accounting-specific that the provider kernel used to hard-code lives
here: the canonical operations and their argument cages, the author-time synonyms
the path-finder ranks with, and the settings-backed tenant→provider binding.

Removing this import from ``app/providers/__init__.py`` leaves a kernel that knows
nothing about accounting and still runs — that is the test of neutrality.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.providers import bindings
from app.providers.credentials import get_tenant_credentials
from app.providers.pathfinder import register_object_synonyms
from app.providers.registry import set_binding_source
from app.providers.vocabulary import (
    CanonicalArgs,
    CanonicalOp,
    IsoDate,
    MoneyStr,
    OpKind,
    ResultKind,
    register_ops,
)

# ── canonical arg models (the grammar cage's typed contract) ──────────────


class ContactLookupArgs(CanonicalArgs):
    id: int | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _need_one(self) -> ContactLookupArgs:
        if self.id is None and not (self.name and self.name.strip()):
            raise ValueError("contact.lookup requires 'id' or a non-empty 'name'")
        return self


class JournalListArgs(CanonicalArgs):
    contact_id: int | None = None
    contact_name: str | None = None
    date_from: IsoDate | None = None
    date_to: IsoDate | None = None

    @model_validator(mode="after")
    def _one_contact_scope(self) -> JournalListArgs:
        # Contradictory scopes must fail loud, not silently prefer one: with both
        # present the name-resolve step would win and the explicit id be ignored.
        if self.contact_id is not None and self.contact_name:
            raise ValueError("journal.list takes contact_id OR contact_name, not both")
        return self


class JournalGetArgs(CanonicalArgs):
    id: str


class JournalCreateArgs(CanonicalArgs):
    date: IsoDate
    amount: MoneyStr
    debit_account: int
    credit_account: int
    title: str
    contact_id: int | None = None
    currency: str = "CHF"


# ── tenant → provider binding (settings-backed today, DB-backed later) ────


class FallbackBindingSource:
    """Reads the deployment's accounting bindings from settings, with DB credentials.

    Provider binding is still settings-backed (explicit DB binding table is a
    later increment). Per-tenant secrets are looked up from the encrypted DB
    store first; when a row is missing the executor falls back to the settings
    fallback (`accounting_tenant_credentials` or global provider secrets).
    """

    async def provider_for_tenant(
        self, tenant_id: UUID | str, session: AsyncSession | None = None
    ) -> str:
        if session is not None:
            db_provider = await bindings.get_tenant_binding(session, tenant_id)
            if db_provider is not None:
                return db_provider
        configured = settings.accounting_provider_bindings or {}
        return configured.get(str(tenant_id), settings.default_accounting_provider)

    async def credentials_for_tenant(
        self, tenant_id: UUID | str, session: AsyncSession | None = None
    ) -> dict[str, str]:
        base = (settings.accounting_tenant_credentials or {}).get(str(tenant_id), {})
        if session is None:
            return base
        db_creds = await get_tenant_credentials(session, tenant_id)
        # Encrypted DB rows win over settings-backed per-tenant secrets.
        return {**base, **db_creds}


# ── registration (import side effects, executed once) ─────────────────────

register_ops(
    CanonicalOp("contact.lookup", OpKind.QUERY, ResultKind.OBJECT, ContactLookupArgs),
    CanonicalOp("journal.list", OpKind.QUERY, ResultKind.LIST, JournalListArgs),
    CanonicalOp("journal.get", OpKind.QUERY, ResultKind.OBJECT, JournalGetArgs),
    CanonicalOp("journal.create", OpKind.MUTATION, ResultKind.OBJECT, JournalCreateArgs),
)

# Author-time only: helps the path-finder rank vendor endpoints. Never runtime.
register_object_synonyms(
    contact={"contact", "person", "associate", "customer", "supplier", "party", "client"},
    journal={
        "journal",
        "entry",
        "entries",
        "booking",
        "bookings",
        "ledger",
        "transaction",
        "transactions",
        "voucher",
        "posting",
    },
)

set_binding_source(FallbackBindingSource())
