"""FastAPI routes for authentication.

`/login` and `/refresh` are public (they are how a caller obtains a token);
`/me` requires a valid access token. Everything else in the app is gated.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginIn, RefreshIn, TokenOut
from app.core.auth import (
    REFRESH,
    Principal,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_principal,
)
from app.core.dependencies import get_db
from app.identity import service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = await service.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        # One generic message for bad email / bad password / inactive user.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    principal = Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return TokenOut(
        access_token=create_access_token(principal),
        refresh_token=create_refresh_token(principal),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    claims = decode_token(payload.refresh_token, expected_type=REFRESH)
    # Re-validate against the DB so a deactivated user is cut off and a role
    # change takes effect — never trust role/is_active frozen in the token.
    user = await service.get_active_user(db, tenant_id=claims.tenant_id, user_id=claims.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user no longer valid")
    principal = Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return TokenOut(
        access_token=create_access_token(principal),
        refresh_token=create_refresh_token(principal),
    )


@router.get("/me", response_model=Principal)
async def me(principal: Principal = Depends(get_current_principal)) -> Principal:
    return principal
