"""
Authentication API routes — WorkOS AuthKit integration.

Provides login (redirect to WorkOS), callback (exchange code), logout, and user info.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database import get_db
from ..services.workos_auth import (
    authenticate_callback,
    get_authorization_url,
    get_current_user,
    get_or_create_user,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


# --- Routes ---


@router.get("/login")
async def login(
    provider: str | None = Query(None, description="OAuth provider: GitHubOAuth, GoogleOAuth, GitLabOAuth, BitbucketOAuth"),
    scope: str | None = Query(None, description="Comma-separated provider scopes (e.g., 'repo' for GitHub private repos)"),
):
    """
    Redirect to WorkOS AuthKit login.

    Optional query params:
    - provider: Force a specific provider (GitHubOAuth, GoogleOAuth, etc.)
    - scope: Additional provider scopes (e.g., 'repo' for GitHub)
    """
    provider_scopes = scope.split(",") if scope else None
    url = get_authorization_url(
        provider=provider,
        provider_scopes=provider_scopes,
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle the WorkOS AuthKit OAuth callback.

    Exchanges the authorization code for tokens, creates/finds the user,
    stores provider OAuth tokens, and sets the session cookie.
    """
    if error:
        return RedirectResponse(url="/login?error=auth_denied", status_code=302)

    if not code:
        return RedirectResponse(url="/login?error=no_code", status_code=302)

    try:
        auth_response = authenticate_callback(code)
    except Exception:
        return RedirectResponse(url="/login?error=auth_failed", status_code=302)

    # Extract data from the WorkOS response
    workos_user = auth_response.user
    access_token = auth_response.access_token

    # Determine provider tokens from oauth_tokens if present
    github_token = None
    gitlab_token = None
    bitbucket_token = None

    if hasattr(auth_response, "oauth_tokens") and auth_response.oauth_tokens:
        oauth_tokens = auth_response.oauth_tokens
        provider_access_token = getattr(oauth_tokens, "access_token", None)
        # Determine which provider this token belongs to based on scopes/provider
        # WorkOS returns the provider in the authentication_method
        if hasattr(auth_response, "authentication_method"):
            method = auth_response.authentication_method
            if method and "github" in str(method).lower():
                github_token = provider_access_token
            elif method and "gitlab" in str(method).lower():
                gitlab_token = provider_access_token
            elif method and "bitbucket" in str(method).lower():
                bitbucket_token = provider_access_token

    # Create or find user in our database
    await get_or_create_user(
        db=db,
        workos_user_id=workos_user.id,
        email=workos_user.email,
        github_access_token=github_token,
        gitlab_access_token=gitlab_token,
        bitbucket_access_token=bitbucket_token,
    )

    await db.commit()

    # Set session cookie and redirect to home
    response = RedirectResponse(url="/", status_code=302)
    is_production = Config.ENVIRONMENT != "development"
    response.set_cookie(
        key="dependiq_session",
        value=access_token,
        max_age=3600,  # 1 hour — refresh handled by WorkOS
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request):
    """
    Logout: clear the session cookie.
    """
    response = Response(
        content='{"message": "Logged out successfully"}',
        media_type="application/json",
    )
    response.delete_cookie(
        key="dependiq_session",
        path="/",
    )
    return response


@router.get("/me", response_model=dict)
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user information.
    """
    from ..models import User

    user: User = await get_current_user(request, db)
    return user.to_dict()
