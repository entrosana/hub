"""Service-layer business validation tests."""

import secrets
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.accounting import service as accounting_service
from app.addresses import service as addresses_service
from app.audit.models import AuditEvent
from app.billing import service as billing_service
from app.contracts import service as contracts_service
from app.core.validation import ValidationError
from app.documents import service as documents_service
from app.expenses import service as expenses_service
from app.identity import service as identity_service
from app.scheduling import service as scheduling_service
from app.signup import service as signup_service
from app.taxes import service as taxes_service

PREFIX = "/api/v1"


async def test_accounting_validation_and_normalization(db):
    tenant_id = uuid4()
    entry = await accounting_service.propose_entry(
        db,
        tenant_id=tenant_id,
        actor_id="test",
        description="  Supplies  ",
        amount_cents=100,
        currency="chf",
    )
    assert entry.description == "Supplies"
    assert entry.currency == "CHF"
    event = (
        (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action == "accounting.entry.propose",
                )
            )
        )
        .scalars()
        .one()
    )
    assert event.after_state["currency"] == "CHF"

    with pytest.raises(ValidationError):
        await accounting_service.propose_entry(
            db,
            tenant_id=tenant_id,
            actor_id="test",
            description="Entry",
            amount_cents=0,
        )


async def test_billing_validation(db):
    await billing_service.issue_invoice(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        number="INV-1",
        family_id="family-1",
        amount_cents=100,
        issued_on=date(2026, 1, 1),
        due_on=date(2026, 1, 1),
    )

    with pytest.raises(ValidationError):
        await billing_service.issue_invoice(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            number="INV-2",
            family_id="family-2",
            amount_cents=100,
            issued_on=date(2026, 1, 2),
            due_on=date(2026, 1, 1),
        )


async def test_contract_validation(db):
    await contracts_service.draft_contract(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        title="Contract",
        template_version="v1",
    )

    with pytest.raises(ValidationError):
        await contracts_service.draft_contract(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            title=" ",
            template_version="v1",
        )


async def test_document_validation(db):
    await documents_service.register_document(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        filename="receipt.pdf",
        mime_type="application/pdf",
        storage_uri="s3://bucket/receipt.pdf",
        size_bytes=0,
    )

    with pytest.raises(ValidationError):
        await documents_service.register_document(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            filename="receipt.pdf",
            mime_type="application/pdf",
            storage_uri="s3://bucket/receipt.pdf",
            size_bytes=-1,
        )


async def test_expense_validation(db):
    await expenses_service.submit_expense(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        description="Lunch",
        amount_cents=100,
    )

    with pytest.raises(ValidationError):
        await expenses_service.submit_expense(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            description="Lunch",
            amount_cents=0,
        )


async def test_schedule_validation(db):
    starts_at = datetime(2026, 1, 1, 10, tzinfo=UTC)
    await scheduling_service.create_schedule(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        title="Class",
        starts_at=starts_at,
        ends_at=datetime(2026, 1, 1, 11, tzinfo=UTC),
    )

    with pytest.raises(ValidationError):
        await scheduling_service.create_schedule(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            title="Class",
            starts_at=starts_at,
            ends_at=starts_at,
        )


async def test_signup_validation(db):
    await signup_service.submit_application(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        student_name="Student",
        parent_name="Parent",
        parent_email="parent@example.com",
    )

    with pytest.raises(ValidationError):
        await signup_service.submit_application(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            student_name=" ",
            parent_name="Parent",
            parent_email="parent@example.com",
        )


async def test_tax_validation(db):
    await taxes_service.draft_filing(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        kind="source_tax",
        period_year=2026,
        period_month=1,
    )

    with pytest.raises(ValidationError):
        await taxes_service.draft_filing(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            kind="source_tax",
            period_year=1999,
        )


async def test_address_validation_and_normalization(db):
    address = await addresses_service.register_address(
        db,
        tenant_id=uuid4(),
        actor_id="test",
        line1="Main Street 1",
        line2=None,
        postcode="8000",
        city="Zurich",
        country="ch",
    )
    assert address.country == "CH"

    with pytest.raises(ValidationError):
        await addresses_service.register_address(
            db,
            tenant_id=uuid4(),
            actor_id="test",
            line1="Main Street 1",
            line2=None,
            postcode="8000",
            city="Zurich",
            country="CHE",
        )


async def test_api_returns_422_for_business_rule(db, client):
    tenant_id = uuid4()
    email = f"{uuid4()}@example.com"
    password = secrets.token_urlsafe(24)
    await identity_service.create_user(
        db,
        tenant_id=tenant_id,
        actor_id="setup",
        name="Admin",
        email=email,
        password=password,
        role="member",
    )
    await db.commit()
    login = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]

    response = await client.post(
        f"{PREFIX}/accounting/entries",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Entry", "amount_cents": 0, "currency": "CHF"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "amount_cents must be greater than zero",
        "field": "amount_cents",
    }
