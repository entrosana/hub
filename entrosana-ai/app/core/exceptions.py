"""Centralized exception handling and a standardized problem-response format.

Router code should raise domain-specific exceptions (``ProviderError`` subclasses,
``HTTPException``, etc.) and let the handlers registered by :func:`add_exception_handlers`
transform them into a uniform JSON response.  This keeps endpoint code free of
status-code mapping and ensures every error is logged once, in one shape.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from app.core.logging import log
from app.core.validation import ValidationError
from app.providers.errors import (
    ArgValidationError,
    ConfirmationRequiredError,
    ExecutionError,
    IdempotencyRequiredError,
    ProviderError,
    SpecError,
    UnknownOpError,
    UnknownProviderError,
    UnsupportedOperationError,
)


class ProblemResponse(JSONResponse):
    """Standard error envelope.

    Mirrors FastAPI's default ``{"detail": ...}`` shape so existing clients keep
    working, while adding ``status`` and ``type`` for richer diagnostics.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        type_: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            headers=headers,
            content={
                "detail": detail,
                "status": status_code,
                "type": type_,
            },
        )


_PROVIDER_STATUS_MAP: dict[type[ProviderError], int] = {
    UnknownOpError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ArgValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    UnsupportedOperationError: status.HTTP_501_NOT_IMPLEMENTED,
    UnknownProviderError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    SpecError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ExecutionError: status.HTTP_502_BAD_GATEWAY,
    ConfirmationRequiredError: status.HTTP_409_CONFLICT,
    IdempotencyRequiredError: status.HTTP_409_CONFLICT,
}


def _provider_status_code(exc: ProviderError) -> int:
    for klass, code in _PROVIDER_STATUS_MAP.items():
        if isinstance(exc, klass):
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


async def provider_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Signature kept broad because Starlette's ``add_exception_handler`` expects
    # ``Callable[[Request, Exception], Response]``; the registered exc_class
    # narrows the dispatch at runtime.
    assert isinstance(exc, ProviderError)
    code = _provider_status_code(exc)
    log.error(
        "provider error",
        exc_info=True,
        path=str(request.url),
        status=code,
        detail=str(exc),
    )
    return ProblemResponse(
        status_code=code,
        detail=str(exc),
        type_=type(exc).__name__,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # See provider_error_handler for the broad signature rationale.
    assert isinstance(exc, HTTPException)
    log.error(
        "http exception",
        path=str(request.url),
        status=exc.status_code,
        detail=exc.detail,
    )
    return ProblemResponse(
        status_code=exc.status_code,
        detail=exc.detail,
        type_="HTTPException",
        headers=dict(exc.headers) if exc.headers else None,
    )


async def catchall_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "unhandled exception",
        exc_info=True,
        path=str(request.url),
        detail=str(exc),
    )
    return ProblemResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="internal server error",
        type_=type(exc).__name__,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ValidationError)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc), "field": exc.field},
    )


def add_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on ``app``."""
    app.add_exception_handler(ProviderError, provider_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, catchall_exception_handler)
