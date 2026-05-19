"""Business logic for identity. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.core.security import hash_password
from app.identity.models import User


async def create_user(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    name: str,
    email: str | None = None,
    password: str | None = None,
) -> User:
    password_hash = hash_password(password) if password else None
    user = await create_for_tenant(
        db,
        User,
        tenant_id,
        name=name,
        email=email,
        password_hash=password_hash,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="identity.user.create",
        target_type="user",
        target_id=str(user.id),
        # NB: password (or its hash) is intentionally NOT in the audit
        # after-state — that would leak it through the signed chain.
        after={"name": name, "email": email, "has_password": password is not None},
    )
    return user
