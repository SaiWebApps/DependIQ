"""
GitHub OAuth service for authentication and token management
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..models import OAuthConnection, User, UserSession


class GitHubOAuthService:
    """Service for GitHub OAuth operations"""

    # GitHub OAuth endpoints
    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_USER_API_URL = "https://api.github.com/user"
    GITHUB_USER_EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        self.redirect_uri = os.getenv(
            "GITHUB_REDIRECT_URI", f"{Config.APP_URL}/api/auth/github/callback"
        )

    def get_authorization_url(self, state: str) -> str:
        """
        Generate GitHub OAuth authorization URL

        Args:
            state: Random state string for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        scopes = "read:user user:email repo"  # Required scopes

        return (
            f"{self.GITHUB_AUTHORIZE_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
        )

    async def exchange_code_for_token(self, code: str) -> dict[str, Any] | None:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from GitHub

        Returns:
            Token data or None if exchange fails
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.GITHUB_TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers={"Accept": "application/json"},
                )

                if response.status_code == 200:
                    return response.json()

                return None
            except Exception as e:
                print(f"Error exchanging code for token: {e}")
                return None

    async def get_github_user_info(self, access_token: str) -> dict[str, Any] | None:
        """
        Get GitHub user information using access token

        Args:
            access_token: GitHub access token

        Returns:
            User information or None if request fails
        """
        async with httpx.AsyncClient() as client:
            try:
                # Get user info
                user_response = await client.get(
                    self.GITHUB_USER_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )

                if user_response.status_code != 200:
                    return None

                user_data = user_response.json()

                # Get user emails
                emails_response = await client.get(
                    self.GITHUB_USER_EMAILS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )

                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    # Get primary email
                    primary_email = next(
                        (e["email"] for e in emails if e.get("primary")),
                        user_data.get("email"),
                    )
                    user_data["email"] = primary_email

                return user_data
            except Exception as e:
                print(f"Error getting GitHub user info: {e}")
                return None

    async def link_github_account(
        self,
        user: User,
        access_token: str,
        github_user_data: dict[str, Any],
        refresh_token: str | None = None,
    ) -> OAuthConnection:
        """
        Link GitHub account to user

        Args:
            user: User to link account to
            access_token: GitHub access token
            github_user_data: GitHub user information
            refresh_token: Optional refresh token

        Returns:
            Created or updated OAuth connection
        """
        # Check if connection already exists
        result = await self.db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user.id, OAuthConnection.provider == "github"
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # Update existing connection
            connection.provider_email = github_user_data.get("email")
            connection.access_token = access_token
            connection.refresh_token = refresh_token
            connection.provider_data = github_user_data
            connection.updated_at = datetime.utcnow()
        else:
            # Create new connection
            connection = OAuthConnection(
                user_id=user.id,
                provider="github",
                provider_user_id=str(github_user_data["id"]),
                provider_email=github_user_data.get("email"),
                access_token=access_token,
                refresh_token=refresh_token,
                scopes="read:user user:email repo",
                provider_data=github_user_data,
            )
            self.db.add(connection)

        await self.db.commit()
        await self.db.refresh(connection)

        return connection

    async def create_user_session(
        self, user: User, access_token: str, expires_in: int = 28800  # 8 hours default
    ) -> UserSession:
        """
        Create user session for GitHub operations

        Args:
            user: User to create session for
            access_token: GitHub access token
            expires_in: Token expiration time in seconds

        Returns:
            Created user session
        """
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        session = UserSession(
            user_id=user.id,
            session_token=access_token,  # Use GitHub token as session token
            expires_at=expires_at,
            session_data={"provider": "github"},
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def get_active_github_token(self, user_id: str) -> str | None:
        """
        Get active GitHub access token for user

        Args:
            user_id: User ID (string or UUID)

        Returns:
            Access token or None if not found/expired
        """
        # Convert string UUID to UUID object if needed
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        # Check OAuth connection
        result = await self.db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user_uuid,
                OAuthConnection.provider == "github",
            )
        )
        connection = result.scalar_one_or_none()

        if connection and connection.access_token:
            return connection.access_token

        # Check user session
        session_result = await self.db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user_uuid,
                UserSession.expires_at > datetime.utcnow(),
            )
            .order_by(UserSession.created_at.desc())
        )
        session = session_result.scalar_one_or_none()

        if session and session.session_data.get("provider") == "github":
            return session.session_token

        return None

    async def revoke_github_access(self, user_id: str) -> bool:
        """
        Revoke GitHub access for user

        Args:
            user_id: User ID (string or UUID)

        Returns:
            True if revoked successfully
        """
        # Convert string UUID to UUID object if needed
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        # Delete OAuth connection
        result = await self.db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user_uuid,
                OAuthConnection.provider == "github",
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            await self.db.delete(connection)

        # Delete associated sessions
        session_result = await self.db.execute(
            select(UserSession).where(UserSession.user_id == user_uuid)
        )
        sessions = session_result.scalars().all()

        for session in sessions:
            if session.session_data.get("provider") == "github":
                await self.db.delete(session)

        await self.db.commit()
        return True


async def get_github_repositories(access_token: str, per_page: int = 30) -> list | None:
    """
    Get user's GitHub repositories

    Args:
        access_token: GitHub access token
        per_page: Number of repositories per page

    Returns:
        List of repositories or None if request fails
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params={
                    "per_page": per_page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator",
                },
            )

            if response.status_code == 200:
                return response.json()

            return None
        except Exception as e:
            print(f"Error getting GitHub repositories: {e}")
            return None


async def get_repository_contents(
    access_token: str, owner: str, repo: str, path: str = ""
) -> Any | None:
    """
    Get repository contents

    Args:
        access_token: GitHub access token
        owner: Repository owner
        repo: Repository name
        path: Path within repository

    Returns:
        Repository contents or None if request fails
    """
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )

            if response.status_code == 200:
                return response.json()

            return None
        except Exception as e:
            print(f"Error getting repository contents: {e}")
            return None
