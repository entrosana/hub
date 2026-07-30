"""DB access for signup.

Generic CRUD lives in `app.core.crud`. Add signup-specific queries
(by parent email, applications awaiting review) here.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.signup.models import Application


async def find_by_parent_email(db: AsyncSession, tenant_id: UUID, email: str) -> list[Application]:
    q = (
        select(Application)
        .where(
            Application.tenant_id == tenant_id,
            Application.parent_email == email,
        )
        .order_by(Application.created_at.desc())
    )
    result = await db.execute(q)
    return list(result.scalars())
