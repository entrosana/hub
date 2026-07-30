"""Business logic for identity. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant, get_for_tenant
from app.core.security import hash_password, verify_password
from app.identity.models import User
from app.identity.repository import find_by_email_global

# Precomputed once at import so login timing does not reveal whether an email
# exists: when the user is unknown we still run a bcrypt verify against this.
_DUMMY_HASH = hash_password("timing-normalisation-not-a-real-password")


async def create_user(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    name: str,
    email: str | None = None,
    password: str | None = None,
    role: str = "member",
) -> User:
    password_hash = hash_password(password) if password else None
    user = await create_for_tenant(
        db,
        User,
        tenant_id,
        name=name,
        email=email,
        password_hash=password_hash,
        role=role,
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
        after={"name": name, "email": email, "role": role, "has_password": password is not None},
    )
    return user


async def get_active_user(db: AsyncSession, *, tenant_id: UUID, user_id: UUID) -> User | None:
    """Load a user within its tenant, only if still active.

    Used on token refresh so deactivation and role changes take effect on the
    next refresh instead of being frozen into the token (adversarial finding:
    stateless refresh bypassed deactivation/role revocation).
    """
    user = await get_for_tenant(db, User, tenant_id, user_id)
    if user is None or not user.is_active:
        return None
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User | None:
    """Verify email + password for login. Returns the User or None.

    Runs a constant-cost bcrypt verify whether or not the email exists, so the
    endpoint does not leak which emails are registered via response timing.
    """
    user = await find_by_email_global(db, email)
    stored_hash = user.password_hash if (user and user.password_hash) else _DUMMY_HASH
    password_ok = verify_password(password, stored_hash)
    if user is None or not user.is_active or not user.password_hash or not password_ok:
        return None
    return user
