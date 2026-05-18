"""Business logic for documents.  All mutations go through audit.record()."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import repository
from app.audit import service as audit


async def create_document(db: AsyncSession, *, tenant_id: str, actor_id: str, name: str):
    obj = await repository.create(db, tenant_id=tenant_id, name=name)
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="documents.document.create",
        target_type="document",
        target_id=str(obj.id),
        after={"name": name},
    )
    return obj
