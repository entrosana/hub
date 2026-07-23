"""FastAPI routes for the natural-language assistant.

``POST /api/v1/assistant/query`` — prose in, executed+audited canonical result out.
Gated by the global auth dependency (mounted in ``app.main``); identity comes from
the verified token. Queries execute; mutations return a preview (never auto-applied).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.schemas import AssistantQueryIn, AssistantQueryOut
from app.core.auth import Principal, get_current_principal
from app.core.dependencies import get_accounting_transport, get_db
from app.dlm.dispatch import dispatch_query
from app.providers.errors import (
    ArgValidationError,
    ExecutionError,
    UnknownOpError,
    UnknownProviderError,
    UnsupportedOperationError,
)
from app.providers.transport import Transport

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantQueryOut)
async def assistant_query(
    body: AssistantQueryIn,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
    transport: Transport = Depends(get_accounting_transport),
) -> AssistantQueryOut:
    try:
        res = await dispatch_query(db, principal, body.input, transport=transport)
    except (UnknownOpError, ArgValidationError) as e:
        # grammar cage rejected the routed tool / args — nothing executed.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except UnsupportedOperationError as e:
        # valid op, but this tenant's provider does not implement it.
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=str(e)) from e
    except UnknownProviderError as e:
        # tenant bound to a provider with no spec — a configuration error.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except ExecutionError as e:
        # the upstream accounting API call failed. (If this was a query, the
        # signed query.requested row is already committed — the trail shows an
        # execution whose outcome row is absent, which is the honest state.)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

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
