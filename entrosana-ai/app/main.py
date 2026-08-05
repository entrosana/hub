"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.accounting.router import router as accounting_router
from app.addresses.router import router as addresses_router
from app.admin.router import router as admin_router
from app.assistant.router import router as assistant_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.contracts.router import router as contracts_router
from app.core.auth import get_current_principal, require_role
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.exceptions import add_exception_handlers
from app.core.logging import configure_logging, log
from app.core.middleware import CorrelationIdMiddleware
from app.core.tracing import setup_tracing
from app.core.validation import ValidationError
from app.dlm.runner import close_anthropic_client
from app.documents.router import router as documents_router
from app.expenses.router import router as expenses_router

# Routers (each module owns one)
from app.identity.router import router as identity_router
from app.providers.transport import close_http_client
from app.scheduling.router import router as scheduling_router
from app.signup.router import router as signup_router
from app.taxes.router import router as taxes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    setup_tracing(app)
    yield
    await close_http_client()
    await close_anthropic_client()
    await engine.dispose()


app = FastAPI(
    title="entrosana-ai",
    description="DLM-backed back-office automation for educational organisations.",
    version=settings.api_version,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

add_exception_handlers(app)


@app.exception_handler(ValidationError)
async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "field": exc.field},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe -- used by Docker HEALTHCHECK + load balancer."""
    return {"status": "ok", "service": "entrosana-ai", "version": settings.api_version}


async def _check_database() -> None:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))


async def _database_probe(status: str) -> dict[str, str] | JSONResponse:
    try:
        await _check_database()
    except Exception as exc:
        log.warning("database health probe failed", error=type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "database unavailable"},
        )
    return {"status": status}


@app.get("/health/live", tags=["meta"])
async def health_live():
    return {"status": "alive"}


@app.get("/health/ready", tags=["meta"])
async def health_ready():
    return await _database_probe("ready")


@app.get("/health/startup", tags=["meta"])
async def health_startup():
    return await _database_probe("started")


# Mount module routers under /api/v1
PREFIX = "/api/v1"

# Auth endpoints are public where they need to be (/login, /refresh); mounted
# without the global auth gate so a caller can obtain a token.
app.include_router(auth_router, prefix=PREFIX)

# Every domain router is gated: no endpoint is reachable without a verified
# access token. This is defense-in-depth on top of get_tenant_id (which also
# requires the principal) — a future route that forgets get_tenant_id is still
# protected.
for r in (
    identity_router,
    audit_router,
    accounting_router,
    scheduling_router,
    contracts_router,
    expenses_router,
    taxes_router,
    signup_router,
    addresses_router,
    billing_router,
    documents_router,
    assistant_router,
):
    app.include_router(r, prefix=PREFIX, dependencies=[Depends(get_current_principal)])

# Admin surface additionally requires the "admin" role (audit: role checks on
# admin/mutating routes).
app.include_router(admin_router, prefix=PREFIX, dependencies=[Depends(require_role("admin"))])
