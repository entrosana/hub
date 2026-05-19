"""FastAPI dependencies shared across routers."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


async def get_tenant_id(x_tenant_id: str | None = Header(None)) -> str:
    """Resolve the current tenant.  Real impl will derive from JWT; this is the stub."""
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id header required")
    return x_tenant_id
