"""Business logic for taxes.  All mutations go through audit.record()."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.taxes import repository


async def create_filing(db: AsyncSession, *, tenant_id: str, actor_id: str, name: str):
    obj = await repository.create(db, tenant_id=tenant_id, name=name)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="taxes.filing.create",
        target_type="filing",
        target_id=str(obj.id),
        after={"name": name},
    )
    return obj
