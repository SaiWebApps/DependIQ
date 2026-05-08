"""
WorkOS AuthKit authentication service.

Sealed sessions: Fernet-encrypted cookies containing access_token,
refresh_token, and user data. Verification via JWKS. Automatic
refresh when the JWT expires.
"""

import logging
import secrets
from datetime import datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import WorkOSClient
from workos.session import (
    AuthenticateWithSessionCookieFailureReason,
    AuthenticateWithSessionCookieSuccessResponse,
    RefreshWithSessionCookieSuccessResponse,
    seal_session_from_auth_response,
)

from ..config import Config
from ..models import User

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "diq_session"
STATE_COOKIE_NAME = "diq_oauth_state"

_workos_client: WorkOSClient | None = None


def validate_workos_config() -> None:
    """Fail fast if required WorkOS config is missing."""
    missing = []
    if not Config.WORKOS_API_KEY:
        missing.append("WORKOS_API_KEY")
    if not Config.WORKOS_CLIENT_ID:
        missing.append("WORKOS_CLIENT_ID")
    if not Config.WORKOS_COOKIE_PASSWORD:
        missing.append("WORKOS_COOKIE_PASSWORD")
    if missing:
        raise RuntimeError(
            f"Missing required WorkOS config: {', '.join(missing)}. "
            "Set these environment variables before starting the app."
        )


def get_workos_client() -> WorkOSClient:
    """Get or create the WorkOS client singleton."""
    global _workos_client
    if _workos_client is None:
        validate_workos_config()
        _workos_client = WorkOSClient(
            api_key=Config.WORKOS_API_KEY,
            client_id=Config.WORKOS_CLIENT_ID,
        )
    return _workos_client


def generate_state() -> str:
    """Generate a CSRF state token for OAuth flow."""
    return secrets.token_urlsafe(32)


def get_authorization_url(
    provider: str | None = None,
    provider_scopes: list[str] | None = None,
) -> tuple[str, str]:
    """
    Generate the WorkOS authorization URL and a CSRF state token.

    Returns:
        Tuple of (authorization_url, state_token)
    """
    client = get_workos_client()
    state = generate_state()

    kwargs: dict = {
        "redirect_uri": Config.WORKOS_REDIRECT_URI,
        "state": state,
        "provider": provider or "authkit",
    }

    if provider_scopes:
        kwargs["provider_scopes"] = provider_scopes

    url = client.user_management.get_authorization_url(**kwargs)
    return url, state


def authenticate_callback(code: str):
    """Exchange an authorization code for tokens and user info."""
    client = get_workos_client()
    return client.user_management.authenticate_with_code(code=code)


def seal_session(auth_response) -> str:
    """Fernet-encrypt access_token + refresh_token + user into a cookie value."""
    return seal_session_from_auth_response(
        access_token=auth_response.access_token,
        refresh_token=auth_response.refresh_token,
        user=auth_response.user.to_dict(),
        impersonator=(
            auth_response.impersonator.to_dict()
            if auth_response.impersonator
            else None
        ),
        cookie_password=Config.WORKOS_COOKIE_PASSWORD,
    )


def verify_or_refresh_session(
    sealed_cookie: str,
) -> tuple[AuthenticateWithSessionCookieSuccessResponse | RefreshWithSessionCookieSuccessResponse | None, str | None]:
    """
    Verify a sealed session. If the JWT is expired, attempt refresh.

    Returns:
        (session_result, new_sealed_cookie_or_None)
        - If valid: (result, None)
        - If refreshed: (result, new_sealed_session_to_set_as_cookie)
        - If dead: (None, None)
    """
    client = get_workos_client()
    session = client.user_management.load_sealed_session(
        session_data=sealed_cookie,
        cookie_password=Config.WORKOS_COOKIE_PASSWORD,
    )

    result = session.authenticate()

    if result.authenticated:
        return (result, None)

    if result.reason == AuthenticateWithSessionCookieFailureReason.INVALID_JWT:
        try:
            refresh_result = session.refresh()
            if refresh_result.authenticated:
                return (refresh_result, refresh_result.sealed_session)
        except Exception as e:
            logger.debug("Session refresh failed: %s", e)

    return (None, None)


async def get_current_user_from_cookie(
    request: Request, db: AsyncSession
) -> User | None:
    """
    Get the current user from the sealed session cookie.
    Handles refresh transparently (stores new cookie in request.state).
    Returns None if not authenticated.
    """
    sealed_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not sealed_cookie:
        return None

    try:
        session_result, new_cookie = verify_or_refresh_session(sealed_cookie)
    except Exception as e:
        logger.debug("Session verification error: %s", e)
        return None

    if not session_result:
        return None

    if new_cookie:
        request.state.refreshed_session = new_cookie

    user_data = session_result.user
    if not user_data:
        return None

    workos_user_id = user_data.get("id")
    if not workos_user_id:
        return None

    result = await db.execute(
        select(User).where(User.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


async def get_current_user(request: Request, db: AsyncSession) -> User:
    """Get authenticated user or raise 401."""
    user = await get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


async def get_or_create_user(
    db: AsyncSession,
    workos_user_id: str,
    email: str,
    github_access_token: str | None = None,
    gitlab_access_token: str | None = None,
    bitbucket_access_token: str | None = None,
) -> User:
    """Find existing user by WorkOS ID or email, or create a new one."""
    result = await db.execute(
        select(User).where(User.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if user:
            user.workos_user_id = workos_user_id
        else:
            user = User(
                email=email.lower(),
                workos_user_id=workos_user_id,
                email_verified=True,
                is_active=True,
            )
            db.add(user)

    if github_access_token is not None:
        user.github_access_token = github_access_token
    if gitlab_access_token is not None:
        user.gitlab_access_token = gitlab_access_token
    if bitbucket_access_token is not None:
        user.bitbucket_access_token = bitbucket_access_token

    user.last_login_at = datetime.utcnow()
    await db.flush()
    return user
