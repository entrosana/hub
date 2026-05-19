"""FastAPI dependencies shared across routers."""
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


async def get_tenant_id(x_tenant_id: str | None = Header(None)) -> UUID:
    """Resolve the current tenant from the X-Tenant-Id header.

    Real auth will derive this from a verified JWT. The header path is the
    development stub used by /docs and integration tests.
    """
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id header required")
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from exc
