"""Business logic for billing. All mutations route through audit.record()."""
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.billing.models import Invoice
from app.core.crud import create_for_tenant


async def issue_invoice(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    number: str,
    family_id: str,
    amount_cents: int,
    currency: str = "CHF",
    issued_on: date,
    due_on: date,
) -> Invoice:
    invoice = await create_for_tenant(
        db, Invoice, tenant_id,
        number=number, family_id=family_id,
        amount_cents=amount_cents, currency=currency,
        issued_on=issued_on, due_on=due_on,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="billing.invoice.issue",
        target_type="invoice",
        target_id=str(invoice.id),
        after={
            "number": number,
            "family_id": family_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "issued_on": issued_on.isoformat(),
            "due_on": due_on.isoformat(),
        },
    )
    return invoice
