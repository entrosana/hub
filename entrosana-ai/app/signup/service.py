"""Business logic for signup.  All mutations go through audit.record()."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.signup import repository


async def create_application(db: AsyncSession, *, tenant_id: str, actor_id: str, name: str):
    obj = await repository.create(db, tenant_id=tenant_id, name=name)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="signup.application.create",
        target_type="application",
        target_id=str(obj.id),
        after={"name": name},
    )
    return obj
