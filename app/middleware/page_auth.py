"""
Page-level authentication middleware for HTML page routes.
Unlike API authentication, this redirects to login instead of returning 401.
"""

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..services.workos_auth import get_current_user_from_cookie as workos_get_user


async def get_current_user_from_cookie(
    request: Request, db: AsyncSession
) -> User | None:
    """
    Get current user from the dependiq_session cookie.
    Returns None if not authenticated (for optional auth).

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object or None
    """
    return await workos_get_user(request, db)


async def require_auth(request: Request, db: AsyncSession):
    """
    Dependency that requires authentication for page routes.
    Redirects to login page if not authenticated.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException 303: Redirects to login if not authenticated
    """
    user = await get_current_user_from_cookie(request, db)

    if not user:
        # Store the original URL to redirect back after login
        return_url = str(request.url.path)
        if request.url.query:
            return_url += f"?{request.url.query}"

        # Redirect to login with return URL
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?return_to={return_url}"},
        )

    return user
