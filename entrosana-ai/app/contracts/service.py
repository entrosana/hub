"""Business logic for contracts. All mutations route through audit.record()."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.contracts.models import Contract
from app.core.crud import create_for_tenant


async def draft_contract(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    title: str,
    template_version: str,
) -> Contract:
    contract = await create_for_tenant(
        db,
        Contract,
        tenant_id,
        title=title,
        template_version=template_version,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="contracts.contract.draft",
        target_type="contract",
        target_id=str(contract.id),
        after={"title": title, "template_version": template_version},
    )
    return contract
