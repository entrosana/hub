"""Authentication — JWT issue/verify and the request Principal.

This is the single source of tenant + actor identity. Every authenticated
request carries a signed access token; `get_current_principal` verifies it and
yields a `Principal` whose `tenant_id` / `user_id` / `role` are trusted.

Nothing downstream may derive tenant identity from a client-supplied header —
that was the pre-auth stub and the root of the cross-tenant breach (audit C1/C2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings

ACCESS = "access"
REFRESH = "refresh"

# auto_error=False so a missing header yields our own 401 (not FastAPI's 403).
_bearer = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    """The verified identity of the caller. Derived ONLY from a signed token."""

    user_id: UUID
    tenant_id: UUID
    role: str = "member"


def _encode(*, principal: Principal, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(principal.user_id),
        "tid": str(principal.tenant_id),
        "role": principal.role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(principal: Principal) -> str:
    return _encode(
        principal=principal,
        token_type=ACCESS,
        ttl=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(principal: Principal) -> str:
    return _encode(
        principal=principal,
        token_type=REFRESH,
        ttl=timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: str) -> Principal:
    """Verify signature + expiry + required claims, return a trusted Principal.

    `algorithms=[jwt_algorithm]` pins the algorithm, so `alg=none` and
    algorithm-confusion attacks are rejected.
    """
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "tid", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("type") != expected_type:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="wrong token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return Principal(
            user_id=UUID(claims["sub"]),
            tenant_id=UUID(claims["tid"]),
            role=claims.get("role", "member"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="malformed token claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Dependency: verify the Bearer access token and yield the Principal.

    Gate every non-public route with this (directly or via `get_tenant_id`).
    """
    if creds is None or not creds.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(creds.credentials, expected_type=ACCESS)


def require_role(*allowed: str):
    """Dependency factory: 403 unless the principal's role is in `allowed`."""

    async def _dep(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return principal

    return _dep
