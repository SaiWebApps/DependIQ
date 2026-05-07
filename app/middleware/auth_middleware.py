"""
Authentication middleware for WorkOS AuthKit session validation.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.workos_auth import get_current_user as workos_get_current_user
from ..services.workos_auth import (
    get_current_user_from_cookie as workos_get_current_user_from_cookie,
)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from session cookie (dependiq_session).

    Raises HTTPException 401 if not authenticated.
    Used for API routes that require authentication.
    """
    return await workos_get_current_user(request, db)


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Get current user if authenticated, None otherwise.

    Use this for routes that can work with or without authentication.
    """
    return await workos_get_current_user_from_cookie(request, db)


async def get_current_active_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current active user (alias for get_current_user).
    """
    return await workos_get_current_user(request, db)


async def get_current_verified_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current user with verified email.

    Raises HTTPException 403 if email not verified.
    """
    user = await workos_get_current_user(request, db)

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required"
        )

    return user
