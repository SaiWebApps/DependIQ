"""
Authentication middleware — FastAPI dependencies for route protection.
"""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.workos_auth import get_current_user as _get_current_user
from ..services.workos_auth import (
    get_current_user_from_cookie as _get_current_user_optional,
)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require authenticated user. Raises 401 if not authenticated."""
    return await _get_current_user(request, db)


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, None otherwise."""
    return await _get_current_user_optional(request, db)
