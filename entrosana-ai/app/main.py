"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.accounting.router import router as accounting_router
from app.addresses.router import router as addresses_router
from app.admin.router import router as admin_router
from app.audit.router import router as audit_router
from app.billing.router import router as billing_router
from app.contracts.router import router as contracts_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.tracing import setup_tracing
from app.documents.router import router as documents_router
from app.expenses.router import router as expenses_router

# Routers (each module owns one)
from app.identity.router import router as identity_router
from app.scheduling.router import router as scheduling_router
from app.signup.router import router as signup_router
from app.taxes.router import router as taxes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    setup_tracing(app)
    yield


app = FastAPI(
    title="entrosana-ai",
    description="DLM-backed back-office automation for educational organisations.",
    version=settings.api_version,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe -- used by Docker HEALTHCHECK + load balancer."""
    return {"status": "ok", "service": "entrosana-ai", "version": settings.api_version}


# Mount module routers under /api/v1
PREFIX = "/api/v1"
for r in (
    identity_router,
    audit_router,
    accounting_router,
    admin_router,
    scheduling_router,
    contracts_router,
    expenses_router,
    taxes_router,
    signup_router,
    addresses_router,
    billing_router,
    documents_router,
):
    app.include_router(r, prefix=PREFIX)
