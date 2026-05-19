"""Business logic for addresses. All mutations route through audit.record()."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.audit import service as audit
from app.core.crud import create_for_tenant


async def register_address(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    line1: str,
    line2: str | None,
    postcode: str,
    city: str,
    country: str = "CH",
) -> Address:
    address = await create_for_tenant(
        db, Address, tenant_id,
        line1=line1, line2=line2,
        postcode=postcode, city=city, country=country,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="addresses.address.register",
        target_type="address",
        target_id=str(address.id),
        after={
            "line1": line1,
            "line2": line2,
            "postcode": postcode,
            "city": city,
            "country": country,
        },
    )
    return address
