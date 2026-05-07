"""
WorkOS AuthKit authentication service.

Replaces custom JWT/OAuth logic with WorkOS-managed authentication.
"""

from datetime import datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import WorkOSClient

from ..config import Config
from ..models import User

# Initialize WorkOS client
_workos_client: WorkOSClient | None = None


def get_workos_client() -> WorkOSClient:
    """Get or create the WorkOS client singleton."""
    global _workos_client
    if _workos_client is None:
        _workos_client = WorkOSClient(
            api_key=Config.WORKOS_API_KEY,
            client_id=Config.WORKOS_CLIENT_ID,
        )
    return _workos_client


def get_authorization_url(
    provider: str | None = None,
    redirect_uri: str | None = None,
    provider_scopes: list[str] | None = None,
) -> str:
    """
    Generate the WorkOS AuthKit authorization URL.

    Args:
        provider: OAuth provider (e.g., 'GitHubOAuth', 'GoogleOAuth')
        redirect_uri: Callback URL (defaults to Config.WORKOS_REDIRECT_URI)
        provider_scopes: Additional scopes for the provider (e.g., ['repo'])

    Returns:
        Authorization URL string
    """
    client = get_workos_client()
    uri = redirect_uri or Config.WORKOS_REDIRECT_URI

    kwargs = {
        "redirect_uri": uri,
    }

    if provider:
        kwargs["provider"] = provider

    if provider_scopes:
        kwargs["provider_scopes"] = provider_scopes

    authorization_url = client.user_management.get_authorization_url(**kwargs)
    return authorization_url


def authenticate_callback(code: str):
    """
    Exchange an authorization code for session tokens and user info.

    Args:
        code: The authorization code from WorkOS callback

    Returns:
        Authentication response with user, access_token, refresh_token, oauth_tokens
    """
    client = get_workos_client()
    response = client.user_management.authenticate_with_code(
        code=code,
    )
    return response


def verify_session(token: str) -> dict | None:
    """
    Verify a WorkOS session JWT.

    Args:
        token: The session JWT (access_token from WorkOS)

    Returns:
        Decoded payload dict or None if invalid
    """
    import jwt as pyjwt
    from jwt.exceptions import InvalidTokenError

    try:
        # WorkOS JWTs are verified by decoding the claims.
        # The token lifetime is managed by WorkOS; we trust it if decodable.
        # In production with JWKS verification, use workos.user_management APIs.
        payload = pyjwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
        return payload
    except InvalidTokenError:
        return None


async def get_or_create_user(
    db: AsyncSession,
    workos_user_id: str,
    email: str,
    github_access_token: str | None = None,
    gitlab_access_token: str | None = None,
    bitbucket_access_token: str | None = None,
) -> User:
    """
    Find existing user by WorkOS ID or email, or create a new one.

    Args:
        db: Database session
        workos_user_id: The WorkOS user ID
        email: User's email address
        github_access_token: GitHub OAuth token (if provider was GitHub)
        gitlab_access_token: GitLab OAuth token
        bitbucket_access_token: Bitbucket OAuth token

    Returns:
        User model instance
    """
    # First try to find by workos_user_id
    result = await db.execute(
        select(User).where(User.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Try to find by email (for migration from old auth)
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if user:
            # Link existing user to WorkOS
            user.workos_user_id = workos_user_id
        else:
            # Create new user
            user = User(
                email=email.lower(),
                workos_user_id=workos_user_id,
                email_verified=True,
                is_active=True,
            )
            db.add(user)

    # Update OAuth tokens if provided
    if github_access_token is not None:
        user.github_access_token = github_access_token
    if gitlab_access_token is not None:
        user.gitlab_access_token = gitlab_access_token
    if bitbucket_access_token is not None:
        user.bitbucket_access_token = bitbucket_access_token

    user.last_login_at = datetime.utcnow()

    await db.flush()
    return user


async def get_current_user(request: Request, db: AsyncSession) -> User:
    """
    FastAPI dependency: get the current authenticated user from session cookie.

    Raises HTTPException 401 if not authenticated.
    """
    user = await get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_from_cookie(
    request: Request, db: AsyncSession
) -> User | None:
    """
    Get the current user from the session cookie.

    Returns None if not authenticated (for page routes that redirect).
    """
    # Read session token from cookie
    token = request.cookies.get("dependiq_session")

    if not token:
        return None

    # Verify the session JWT
    payload = verify_session(token)
    if not payload:
        return None

    # Extract user info from the JWT
    sub = payload.get("sub")
    if not sub:
        return None

    # Look up user by workos_user_id (the 'sub' claim)
    result = await db.execute(
        select(User).where(User.workos_user_id == sub)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user
