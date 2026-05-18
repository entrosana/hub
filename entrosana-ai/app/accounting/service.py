"""Business logic for accounting.  All mutations go through audit.record()."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import repository
from app.audit import service as audit


async def create_entry(db: AsyncSession, *, tenant_id: str, actor_id: str, name: str):
    obj = await repository.create(db, tenant_id=tenant_id, name=name)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="accounting.entry.create",
        target_type="entry",
        target_id=str(obj.id),
        after={"name": name},
    )
    return obj
