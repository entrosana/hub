"""Business logic for accounting. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Entry
from app.audit import service as audit
from app.core.crud import create_for_tenant


async def propose_entry(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    description: str,
    amount_cents: int,
    currency: str = "CHF",
) -> Entry:
    """Create a booking-proposal entry. Status starts at 'proposed' and
    needs explicit approval before it gets pushed to CashCtrl."""
    entry = await create_for_tenant(
        db,
        Entry,
        tenant_id,
        description=description,
        amount_cents=amount_cents,
        currency=currency,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="accounting.entry.propose",
        target_type="entry",
        target_id=str(entry.id),
        after={
            "description": description,
            "amount_cents": amount_cents,
            "currency": currency,
        },
    )
    return entry
