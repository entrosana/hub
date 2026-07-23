"""FastAPI dependencies shared across routers.

`get_tenant_id` and `get_actor_id` derive identity from the verified access
token (`get_current_principal`) — never from a client header. Every router that
depends on `get_tenant_id` is therefore authenticated and tenant-scoped to the
token's tenant, closing the unauthenticated cross-tenant path (audit C1/C2).
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


async def get_tenant_id(
    principal: Principal = Depends(get_current_principal),
) -> UUID:
    """The acting tenant — from the verified token, never a header."""
    return principal.tenant_id


async def get_actor_id(
    principal: Principal = Depends(get_current_principal),
) -> str:
    """The authenticated actor id (str), for audit attribution (audit H1)."""
    return str(principal.user_id)
