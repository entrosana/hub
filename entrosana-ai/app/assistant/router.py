"""FastAPI routes for the natural-language assistant.

``POST /api/v1/assistant/query`` — prose in, executed+audited canonical result out.
Gated by the global auth dependency (mounted in ``app.main``); identity comes from
the verified token. Queries execute; mutations return a preview (never auto-applied).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.schemas import AssistantQueryIn, AssistantQueryOut
from app.core.auth import Principal, get_current_principal
from app.core.dependencies import get_accounting_transport, get_db
from app.dlm.dispatch import dispatch_query
from app.providers.transport import Transport

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantQueryOut)
async def assistant_query(
    body: AssistantQueryIn,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
    transport: Transport = Depends(get_accounting_transport),
) -> AssistantQueryOut:
    res = await dispatch_query(db, principal, body.input, transport=transport)

    # dispatch_query owns persistence (two-phase signed audit) — no commit here.
    return AssistantQueryOut(
        tool=res.tool,
        args=res.args,
        kind=res.kind,
        executed=res.executed,
        count=res.count,
        source=res.source,
        intent_hash=res.intent_hash,
        result=res.result,
        summary=res.summary,
    )
