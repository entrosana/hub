"""Business logic for admin. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Person
from app.audit import service as audit
from app.core.crud import create_for_tenant


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
