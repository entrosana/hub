"""Coverage for thin domain repositories and routers."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.accounting import router as accounting_router
from app.accounting.schemas import EntryIn
from app.addresses import router as addresses_router
from app.addresses.schemas import AddressIn
from app.billing import router as billing_router
from app.billing.schemas import InvoiceIn
from app.contracts import router as contracts_router
from app.contracts.schemas import ContractIn
from app.documents import router as documents_router
from app.documents.schemas import DocumentIn
from app.expenses import router as expenses_router
from app.expenses.schemas import ExpenseIn
from app.scheduling import router as scheduling_router
from app.scheduling.schemas import ScheduleIn
from app.signup import repository as signup_repository
from app.signup import router as signup_router
from app.signup.schemas import ApplicationIn
from app.taxes import router as taxes_router
from app.taxes.schemas import FilingIn

pytestmark = pytest.mark.anyio


async def test_domain_routers_create_and_filter_records(db):
    tenant = uuid4()
    actor = "coverage-actor"

    entry = await accounting_router.propose_entry(
        EntryIn(description="Tuition", amount_cents=1200, currency="CHF"),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert (await accounting_router.list_entries(status="proposed", tenant_id=tenant, db=db)) == [
        entry
    ]
    assert await accounting_router.list_entries(status="missing", tenant_id=tenant, db=db) == []
    assert await accounting_router.list_entries(tenant_id=tenant, db=db) == [entry]

    address = await addresses_router.register_address(
        AddressIn(line1="Main Street 1", postcode="8000", city="Zürich", country="CH"),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert (await addresses_router.list_addresses(postcode="8000", tenant_id=tenant, db=db)) == [
        address
    ]
    assert await addresses_router.list_addresses(postcode="9999", tenant_id=tenant, db=db) == []

    invoice = await billing_router.issue_invoice(
        InvoiceIn(
            number="INV-1",
            family_id="family-1",
            amount_cents=5000,
            currency="CHF",
            issued_on=date(2026, 1, 1),
            due_on=date(2026, 1, 15),
        ),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert (
        await billing_router.list_invoices(overdue_as_of=date(2026, 2, 1), tenant_id=tenant, db=db)
    ) == [invoice]
    assert await billing_router.list_invoices(family_id="family-1", tenant_id=tenant, db=db) == [
        invoice
    ]
    assert await billing_router.list_invoices(family_id="other", tenant_id=tenant, db=db) == []

    contract = await contracts_router.draft_contract(
        ContractIn(title="Terms", template_version="v1"),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert (
        await contracts_router.list_contracts(awaiting_signature=True, tenant_id=tenant, db=db)
    ) == []
    assert await contracts_router.list_contracts(tenant_id=tenant, db=db) == [contract]

    document = await documents_router.register_document(
        DocumentIn(
            filename="receipt.pdf",
            mime_type="application/pdf",
            storage_uri="s3://receipts/1",
            size_bytes=12,
        ),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert await documents_router.list_documents(tenant_id=tenant, db=db) == [document]
    assert (
        await documents_router.list_documents(classification="invoice", tenant_id=tenant, db=db)
        == []
    )

    expense = await expenses_router.submit_expense(
        ExpenseIn(description="Books", amount_cents=900, currency="CHF"),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert await expenses_router.list_expenses(pending=True, tenant_id=tenant, db=db) == [expense]
    assert await expenses_router.list_expenses(pending=False, tenant_id=tenant, db=db) == [expense]

    starts = datetime.now(UTC).replace(microsecond=0)
    schedule = await scheduling_router.create_schedule(
        ScheduleIn(title="Lesson", starts_at=starts, ends_at=starts + timedelta(hours=1)),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert (
        await scheduling_router.list_schedules(
            start=starts - timedelta(minutes=1),
            end=starts + timedelta(hours=2),
            tenant_id=tenant,
            db=db,
        )
    ) == [schedule]
    assert await scheduling_router.list_schedules(tenant_id=tenant, db=db) == [schedule]

    application = await signup_router.submit_application(
        ApplicationIn(
            student_name="Student",
            parent_name="Parent",
            parent_email="parent@example.com",
        ),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert await signup_router.list_applications(tenant_id=tenant, db=db) == [application]
    assert await signup_repository.find_by_parent_email(db, tenant, "parent@example.com") == [
        application
    ]
    assert await signup_repository.find_by_parent_email(db, tenant, "missing@example.com") == []

    filing = await taxes_router.draft_filing(
        FilingIn(kind="ahv_iv", period_year=2026, period_month=1),
        tenant_id=tenant,
        actor_id=actor,
        db=db,
    )
    assert await taxes_router.list_filings(year=2026, tenant_id=tenant, db=db) == [filing]
    assert await taxes_router.list_filings(year=2025, tenant_id=tenant, db=db) == []

    await db.commit()
