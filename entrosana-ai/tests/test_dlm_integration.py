"""Prerequisites for wiring the DLM into the modules.

M6: an explicit numeric/ISO date range must survive normalization + routing into
    the tool call's args (else scoped queries silently run unscoped).
M4: audit.record_dlm() must persist a signed DLMInteraction row (the runner's
    contract required it, but the function did not exist and was never called).
"""

import uuid

from sqlalchemy import select

from app.audit import service as audit
from app.audit.models import DLMInteraction
from app.dlm.gateway import DLMGateway

# ── M6 — date scope survives into the tool call ──────────────────────────

async def test_swiss_dmy_range_survives_into_tool_call():
    routed = await DLMGateway.for_mock().route_intent(
        "payments of Anna Müller from 01.05.2026 to 31.05.2026"
    )
    assert routed.tool == "cashctrl.journal_list"
    assert routed.args.get("contact_name") == "Anna Müller"
    assert routed.args.get("date_from") == "2026-05-01"
    assert routed.args.get("date_to") == "2026-05-31"


async def test_iso_range_without_contact_survives():
    routed = await DLMGateway.for_mock().route_intent(
        "journal entries from 2026-03-01 to 2026-03-31"
    )
    assert routed.args.get("date_from") == "2026-03-01"
    assert routed.args.get("date_to") == "2026-03-31"


async def test_month_name_range_still_works():
    routed = await DLMGateway.for_mock().route_intent("show May bookings")
    assert routed.args.get("date_from") == "2026-05-01"
    assert routed.args.get("date_to") == "2026-05-31"


# ── M4 — DLMInteraction row is written + signed ──────────────────────────

async def test_record_dlm_writes_signed_row(db):
    tenant = uuid.uuid4()
    runner_result = {
        "output": '{"tool":"cashctrl.journal_list","args":{}}',
        "model_version": "claude-sonnet-4-6",
        "prompt_version": "v0.1.0",
        "retrieval_keys": ["k2", "k1"],
        "tokens_in": 42,
        "tokens_out": 7,
    }
    await audit.record_dlm(
        db, tenant_id=tenant,
        input_payload={"user_input": "list journals"},
        runner_result=runner_result,
    )
    await db.flush()

    row = (
        await db.execute(select(DLMInteraction).where(DLMInteraction.tenant_id == tenant))
    ).scalar_one()
    assert row.model_version == "claude-sonnet-4-6"
    assert row.prompt_version == "v0.1.0"
    assert row.temperature == 0.0
    assert row.retrieval_keys == ["k1", "k2"]  # canonicalised (sorted)
    assert row.output_payload["output"].startswith("{")
    assert len(row.hmac) == 64  # sha256 hexdigest


async def test_record_dlm_links_to_audit_event(db):
    tenant = uuid.uuid4()
    event = await audit.record(
        db, tenant_id=tenant, actor_id="a", action="billing.invoice.issue",
        target_type="invoice", target_id="1",
    )
    row = await audit.record_dlm(
        db, tenant_id=tenant,
        input_payload={"user_input": "issue an invoice"},
        runner_result={"output": "", "model_version": "m", "prompt_version": "p"},
        audit_event_id=event.id,
    )
    assert row.audit_event_id == event.id
