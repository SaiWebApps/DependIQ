"""
Page-level authentication — redirects to login instead of returning 401.
"""

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.workos_auth import get_current_user_from_cookie


async def require_page_auth(request: Request, db: AsyncSession):
    """Require authentication for page routes. Redirects to /login if not authenticated."""
    user = await get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user
