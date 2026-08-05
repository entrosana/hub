"""Business logic for expenses. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.core.validation import require_currency, require_non_empty, require_positive_amount
from app.expenses.models import Expense


async def submit_expense(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    description: str,
    amount_cents: int,
    currency: str = "CHF",
    receipt_document_id: str | None = None,
) -> Expense:
    description = require_non_empty(description, "description")
    amount_cents = require_positive_amount(amount_cents)
    currency = require_currency(currency)
    expense = await create_for_tenant(
        db,
        Expense,
        tenant_id,
        description=description,
        amount_cents=amount_cents,
        currency=currency,
        receipt_document_id=receipt_document_id,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="expenses.expense.submit",
        target_type="expense",
        target_id=str(expense.id),
        after={
            "description": description,
            "amount_cents": amount_cents,
            "currency": currency,
            "receipt_document_id": receipt_document_id,
        },
    )
    return expense
