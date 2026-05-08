"""
Authentication API routes — WorkOS AuthKit integration.

Login (redirect to WorkOS with CSRF state), callback (validate state,
exchange code, seal session), logout, and user info.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database import get_db
from ..services.workos_auth import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    authenticate_callback,
    get_authorization_url,
    get_current_user,
    get_or_create_user,
    seal_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class MessageResponse(BaseModel):
    message: str


def _set_session_cookie(response: Response, sealed: str) -> None:
    """Set the sealed session cookie with correct attributes."""
    is_production = Config.ENVIRONMENT != "development"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sealed,
        max_age=400 * 24 * 60 * 60,
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
    )


@router.get("/login")
async def login(
    provider: str | None = Query(None),
    scope: str | None = Query(None),
):
    """Redirect to WorkOS AuthKit login with CSRF state."""
    provider_scopes = scope.split(",") if scope else None
    url, state = get_authorization_url(
        provider=provider,
        provider_scopes=provider_scopes,
    )

    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        max_age=600,
        httponly=True,
        secure=Config.ENVIRONMENT != "development",
        samesite="lax",
        path="/",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle WorkOS OAuth callback. Validates state, exchanges code, sets session."""
    if error:
        return RedirectResponse(url="/login?error=auth_denied", status_code=302)

    if not code:
        return RedirectResponse(url="/login?error=no_code", status_code=302)

    expected_state = request.cookies.get(STATE_COOKIE_NAME)
    if not state or not expected_state or state != expected_state:
        logger.warning(
            "OAuth state mismatch: expected=%s got=%s", expected_state, state
        )
        return RedirectResponse(url="/login?error=invalid_state", status_code=302)

    try:
        auth_response = authenticate_callback(code)
    except Exception as e:
        logger.error(
            "WorkOS authenticate_with_code failed: %s: %s", type(e).__name__, e
        )
        return RedirectResponse(url="/login?error=auth_failed", status_code=302)

    workos_user = auth_response.user

    github_token = None
    gitlab_token = None
    bitbucket_token = None

    if hasattr(auth_response, "oauth_tokens") and auth_response.oauth_tokens:
        oauth_tokens = auth_response.oauth_tokens
        provider_access_token = getattr(oauth_tokens, "access_token", None)
        if hasattr(auth_response, "authentication_method"):
            method = auth_response.authentication_method
            if method and "github" in str(method).lower():
                github_token = provider_access_token
            elif method and "gitlab" in str(method).lower():
                gitlab_token = provider_access_token
            elif method and "bitbucket" in str(method).lower():
                bitbucket_token = provider_access_token

    await get_or_create_user(
        db=db,
        workos_user_id=workos_user.id,
        email=workos_user.email,
        github_access_token=github_token,
        gitlab_access_token=gitlab_token,
        bitbucket_access_token=bitbucket_token,
    )
    await db.commit()

    sealed = seal_session(auth_response)

    response = RedirectResponse(url="/", status_code=302)
    _set_session_cookie(response, sealed)
    response.delete_cookie(key=STATE_COOKIE_NAME, path="/")
    return response


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """Clear the session cookie."""
    response = Response(
        content='{"message": "Logged out successfully"}',
        media_type="application/json",
    )
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", response_model=dict)
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user information."""
    from ..models import User

    user: User = await get_current_user(request, db)
    return user.to_dict()
