"""Business logic for signup. All mutations route through audit.record()."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.signup.models import Application


async def submit_application(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    student_name: str,
    parent_name: str,
    parent_email: str,
) -> Application:
    application = await create_for_tenant(
        db, Application, tenant_id,
        student_name=student_name,
        parent_name=parent_name,
        parent_email=parent_email,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="signup.application.submit",
        target_type="application",
        target_id=str(application.id),
        after={
            "student_name": student_name,
            "parent_name": parent_name,
            "parent_email": parent_email,
        },
    )
    return application
