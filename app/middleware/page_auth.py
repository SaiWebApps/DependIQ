"""
Page-level authentication middleware for HTML page routes.
Unlike API authentication, this redirects to login instead of returning 401.
"""


from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..services.token_service import verify_token


async def get_current_user_from_cookie(
    request: Request, db: AsyncSession
) -> User | None:
    """
    Get current user from JWT token in Authorization header or cookie.
    Returns None if not authenticated (for optional auth).

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object or None
    """
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    token = None

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")

    # If no token in header, try cookie
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        return None

    # Verify token
    payload = verify_token(token, token_type="access")
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    # Get user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


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
        RedirectResponse: Redirects to login if not authenticated
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
