"""Integration tests for domain service-layer create paths.

Each test exercises a service function end-to-end through the database,
including the audit record it is required to write.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.accounting import service as accounting
from app.accounting.models import Entry
from app.addresses import service as addresses
from app.addresses.models import Address
from app.admin import service as admin
from app.admin.models import Person
from app.audit import service as audit
from app.audit.models import AuditEvent
from app.billing import service as billing
from app.billing.models import Invoice
from app.contracts import service as contracts
from app.contracts.models import Contract
from app.core.crud import get_for_tenant, list_for_tenant
from app.documents import service as documents
from app.documents.models import Document
from app.expenses import service as expenses
from app.expenses.models import Expense
from app.identity import service as identity
from app.identity.models import User
from app.scheduling import service as scheduling
from app.scheduling.models import Schedule
from app.signup import service as signup
from app.signup.models import Application
from app.taxes import service as taxes
from app.taxes.models import Filing


async def _assert_audit_event(db, tenant_id, action, target_id, *, after):
    """Check that a single signed audit event exists matching the mutation."""
    events = list(
        (
            await db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action == action,
                    AuditEvent.target_id == str(target_id),
                )
                .order_by(AuditEvent.seq.asc())
            )
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].after_state == after
    assert events[0].hmac is not None
    assert events[0].prev_hmac is not None


# ── accounting ───────────────────────────────────────────────────────────────


async def test_accounting_propose_entry(db):
    tenant = uuid4()
    entry = await accounting.propose_entry(
        db,
        tenant_id=tenant,
        actor_id="actor",
        description="Course fee",
        amount_cents=12000,
        currency="CHF",
    )
    assert isinstance(entry, Entry)
    assert entry.tenant_id == tenant
    assert entry.description == "Course fee"
    assert entry.amount_cents == 12000
    assert entry.currency == "CHF"
    assert entry.status == "proposed"
    await _assert_audit_event(
        db,
        tenant,
        "accounting.entry.propose",
        entry.id,
        after={"description": "Course fee", "amount_cents": 12000, "currency": "CHF"},
    )


# ── addresses ────────────────────────────────────────────────────────────────


async def test_addresses_register_address(db):
    tenant = uuid4()
    address = await addresses.register_address(
        db,
        tenant_id=tenant,
        actor_id="actor",
        line1="Musterstrasse 1",
        line2="c/o Müller",
        postcode="8000",
        city="Zürich",
        country="CH",
    )
    assert isinstance(address, Address)
    assert address.tenant_id == tenant
    assert address.city == "Zürich"
    assert address.country == "CH"
    await _assert_audit_event(
        db,
        tenant,
        "addresses.address.register",
        address.id,
        after={
            "line1": "Musterstrasse 1",
            "line2": "c/o Müller",
            "postcode": "8000",
            "city": "Zürich",
            "country": "CH",
        },
    )


# ── admin ────────────────────────────────────────────────────────────────────


async def test_admin_create_person(db):
    tenant = uuid4()
    person = await admin.create_person(
        db,
        tenant_id=tenant,
        actor_id="actor",
        name="Anna Meier",
        kind="student",
        email="anna@example.com",
    )
    assert isinstance(person, Person)
    assert person.tenant_id == tenant
    assert person.name == "Anna Meier"
    assert person.kind == "student"
    assert person.email == "anna@example.com"
    await _assert_audit_event(
        db,
        tenant,
        "admin.person.create",
        person.id,
        after={"name": "Anna Meier", "kind": "student", "email": "anna@example.com"},
    )


# ── billing ──────────────────────────────────────────────────────────────────


async def test_billing_issue_invoice(db):
    tenant = uuid4()
    issued = date(2026, 1, 15)
    due = date(2026, 2, 15)
    invoice = await billing.issue_invoice(
        db,
        tenant_id=tenant,
        actor_id="actor",
        number="INV-2026-001",
        family_id="family-1",
        amount_cents=25000,
        currency="CHF",
        issued_on=issued,
        due_on=due,
    )
    assert isinstance(invoice, Invoice)
    assert invoice.tenant_id == tenant
    assert invoice.number == "INV-2026-001"
    assert invoice.status == "open"
    await _assert_audit_event(
        db,
        tenant,
        "billing.invoice.issue",
        invoice.id,
        after={
            "number": "INV-2026-001",
            "family_id": "family-1",
            "amount_cents": 25000,
            "currency": "CHF",
            "issued_on": issued.isoformat(),
            "due_on": due.isoformat(),
        },
    )


# ── contracts ────────────────────────────────────────────────────────────────


async def test_contracts_draft_contract(db):
    tenant = uuid4()
    contract = await contracts.draft_contract(
        db,
        tenant_id=tenant,
        actor_id="actor",
        title="Care contract 2026",
        template_version="v1.0",
    )
    assert isinstance(contract, Contract)
    assert contract.tenant_id == tenant
    assert contract.status == "draft"
    await _assert_audit_event(
        db,
        tenant,
        "contracts.contract.draft",
        contract.id,
        after={"title": "Care contract 2026", "template_version": "v1.0"},
    )


# ── documents ────────────────────────────────────────────────────────────────


async def test_documents_register_document(db):
    tenant = uuid4()
    document = await documents.register_document(
        db,
        tenant_id=tenant,
        actor_id="actor",
        filename="receipt.pdf",
        mime_type="application/pdf",
        storage_uri="s3://bucket/tenant/receipt.pdf",
        size_bytes=1024,
    )
    assert isinstance(document, Document)
    assert document.tenant_id == tenant
    assert document.filename == "receipt.pdf"
    assert document.status == "uploaded"
    await _assert_audit_event(
        db,
        tenant,
        "documents.document.register",
        document.id,
        after={
            "filename": "receipt.pdf",
            "mime_type": "application/pdf",
            "storage_uri": "s3://bucket/tenant/receipt.pdf",
            "size_bytes": 1024,
        },
    )


# ── expenses ─────────────────────────────────────────────────────────────────


async def test_expenses_submit_expense(db):
    tenant = uuid4()
    expense = await expenses.submit_expense(
        db,
        tenant_id=tenant,
        actor_id="actor",
        description="Office supplies",
        amount_cents=4500,
        currency="CHF",
        receipt_document_id="doc-123",
    )
    assert isinstance(expense, Expense)
    assert expense.tenant_id == tenant
    assert expense.status == "submitted"
    await _assert_audit_event(
        db,
        tenant,
        "expenses.expense.submit",
        expense.id,
        after={
            "description": "Office supplies",
            "amount_cents": 4500,
            "currency": "CHF",
            "receipt_document_id": "doc-123",
        },
    )


# ── identity ─────────────────────────────────────────────────────────────────


async def test_identity_create_user(db):
    tenant = uuid4()
    user_password = secrets.token_urlsafe(24)
    user = await identity.create_user(
        db,
        tenant_id=tenant,
        actor_id="actor",
        name="Lehrer",
        email="lehrer@example.com",
        password=user_password,
        role="admin",
    )
    assert isinstance(user, User)
    assert user.tenant_id == tenant
    assert user.email == "lehrer@example.com"
    assert user.role == "admin"
    assert user.is_active is True
    assert user.password_hash is not None
    await _assert_audit_event(
        db,
        tenant,
        "identity.user.create",
        user.id,
        after={
            "name": "Lehrer",
            "email": "lehrer@example.com",
            "role": "admin",
            "has_password": True,
        },
    )


async def test_identity_get_active_user(db):
    tenant = uuid4()
    user = await identity.create_user(
        db,
        tenant_id=tenant,
        actor_id="actor",
        name="Lehrer",
        email="active@example.com",
    )
    found = await identity.get_active_user(db, tenant_id=tenant, user_id=user.id)
    assert found == user

    user.is_active = False
    await db.flush()
    gone = await identity.get_active_user(db, tenant_id=tenant, user_id=user.id)
    assert gone is None

    assert await identity.get_active_user(db, tenant_id=tenant, user_id=uuid4()) is None


async def test_identity_authenticate(db):
    tenant = uuid4()
    user_password = secrets.token_urlsafe(24)
    user = await identity.create_user(
        db,
        tenant_id=tenant,
        actor_id="actor",
        name="Lehrer",
        email="auth@example.com",
        password=user_password,
    )
    wrong_password = secrets.token_urlsafe(24)
    assert await identity.authenticate(db, email="auth@example.com", password=user_password) == user
    assert (
        await identity.authenticate(db, email="auth@example.com", password=wrong_password) is None
    )
    assert (
        await identity.authenticate(db, email="missing@example.com", password=user_password) is None
    )

    user.is_active = False
    await db.flush()
    assert await identity.authenticate(db, email="auth@example.com", password=user_password) is None


# ── scheduling ───────────────────────────────────────────────────────────────


async def test_scheduling_create_schedule(db):
    tenant = uuid4()
    starts = datetime.now(UTC)
    ends = starts + timedelta(hours=2)
    schedule = await scheduling.create_schedule(
        db,
        tenant_id=tenant,
        actor_id="actor",
        title="Piano lesson",
        starts_at=starts,
        ends_at=ends,
        room="Studio A",
    )
    assert isinstance(schedule, Schedule)
    assert schedule.tenant_id == tenant
    assert schedule.title == "Piano lesson"
    assert schedule.room == "Studio A"
    await _assert_audit_event(
        db,
        tenant,
        "scheduling.schedule.create",
        schedule.id,
        after={
            "title": "Piano lesson",
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
            "room": "Studio A",
        },
    )


# ── signup ───────────────────────────────────────────────────────────────────


async def test_signup_submit_application(db):
    tenant = uuid4()
    application = await signup.submit_application(
        db,
        tenant_id=tenant,
        actor_id="actor",
        student_name="Max Muster",
        parent_name="Maria Muster",
        parent_email="maria@example.com",
    )
    assert isinstance(application, Application)
    assert application.tenant_id == tenant
    assert application.status == "received"
    await _assert_audit_event(
        db,
        tenant,
        "signup.application.submit",
        application.id,
        after={
            "student_name": "Max Muster",
            "parent_name": "Maria Muster",
            "parent_email": "maria@example.com",
        },
    )


# ── taxes ────────────────────────────────────────────────────────────────────


async def test_taxes_draft_filing(db):
    tenant = uuid4()
    filing = await taxes.draft_filing(
        db,
        tenant_id=tenant,
        actor_id="actor",
        kind="AHV",
        period_year=2026,
        period_month=3,
    )
    assert isinstance(filing, Filing)
    assert filing.tenant_id == tenant
    assert filing.status == "draft"
    await _assert_audit_event(
        db,
        tenant,
        "taxes.filing.draft",
        filing.id,
        after={"kind": "AHV", "period_year": 2026, "period_month": 3},
    )


# ── cross-cutting: tenant isolation and chain integrity ───────────────────────


async def test_tenant_isolation_for_created_records(db):
    tenant_a, tenant_b = uuid4(), uuid4()
    address = await addresses.register_address(
        db,
        tenant_id=tenant_a,
        actor_id="actor",
        line1="A",
        line2=None,
        postcode="0000",
        city="Alpha",
    )
    assert address.tenant_id == tenant_a
    found = await get_for_tenant(db, Address, tenant_a, address.id)
    assert found == address
    missing = await get_for_tenant(db, Address, tenant_b, address.id)
    assert missing is None
    assert await list_for_tenant(db, Address, tenant_b) == []


async def test_audit_chain_verifies_after_multiple_service_calls(db):
    tenant = uuid4()
    await accounting.propose_entry(
        db, tenant_id=tenant, actor_id="a", description="One", amount_cents=100
    )
    await addresses.register_address(
        db, tenant_id=tenant, actor_id="b", line1="Two", line2=None, postcode="0000", city="Beta"
    )
    ok, n, bad = await audit.verify_chain(db, tenant)
    assert ok is True
    assert n == 2
    assert bad is None


async def test_audit_chain_is_tenant_isolated_via_services(db):
    tenant_a, tenant_b = uuid4(), uuid4()
    await admin.create_person(db, tenant_id=tenant_a, actor_id="a", name="A", kind="student")
    await signup.submit_application(
        db,
        tenant_id=tenant_b,
        actor_id="b",
        student_name="B",
        parent_name="P",
        parent_email="p@example.com",
    )
    ok_a, n_a, _ = await audit.verify_chain(db, tenant_a)
    ok_b, n_b, _ = await audit.verify_chain(db, tenant_b)
    assert ok_a and n_a == 1
    assert ok_b and n_b == 1
