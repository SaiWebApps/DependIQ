"""GitHub OAuth service — single source of truth for all GitHub OAuth operations."""

from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..models import User
from ..models.oauth_connection import OAuthConnection


class GitHubOAuthService:
    """Handles the GitHub OAuth dance and user management."""

    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client_id = Config.GITHUB_CLIENT_ID
        self.client_secret = Config.GITHUB_CLIENT_SECRET
        self.redirect_uri = Config.GITHUB_REDIRECT_URI
        self.scopes = "read:user user:email"

    def get_authorize_url(self, state: str) -> str:
        """Build the GitHub authorization URL."""
        params = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": self.scopes,
                "state": state,
            }
        )
        return f"{self.AUTHORIZE_URL}?{params}"

    async def exchange_code_for_token(self, code: str) -> str | None:
        """Exchange authorization code for access token. Returns token or None."""
        async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "error" in data:
                return None
            return data.get("access_token")

    async def get_github_user(self, access_token: str) -> dict[str, Any] | None:
        """Fetch GitHub user profile and primary email."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
            user_resp = await client.get(self.USER_URL, headers=headers)
            if user_resp.status_code != 200:
                return None
            user_data = user_resp.json()

            # Fetch emails if no public email
            if not user_data.get("email"):
                emails_resp = await client.get(self.EMAILS_URL, headers=headers)
                if emails_resp.status_code == 200:
                    for email in emails_resp.json():
                        if email.get("primary") and email.get("verified"):
                            user_data["email"] = email["email"]
                            break

            return user_data if user_data.get("email") else None

    async def get_or_create_user(
        self, github_user: dict, access_token: str
    ) -> User | None:
        """Find existing user by GitHub ID or email, or create a new one.

        Links OAuthConnection.
        """
        github_id = str(github_user["id"])
        email = github_user["email"].lower()

        # Check if OAuth connection exists
        result = await self.db.execute(
            select(OAuthConnection).where(
                OAuthConnection.provider == "github",
                OAuthConnection.provider_user_id == github_id,
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # Update token
            connection.access_token = access_token
            await self.db.commit()
            # Fetch user
            result = await self.db.execute(
                select(User).where(User.id == connection.user_id)
            )
            return result.scalar_one_or_none()

        # Check if user exists by email
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            # Create new user
            user = User(email=email, email_verified=True, is_active=True)
            self.db.add(user)
            await self.db.flush()

        # Create OAuth connection
        connection = OAuthConnection(
            user_id=user.id,
            provider="github",
            provider_user_id=github_id,
            access_token=access_token,
            provider_email=github_user.get("email", ""),
        )
        self.db.add(connection)
        await self.db.commit()
        await self.db.refresh(user)
        return user


# --- Standalone functions imported by other modules ---


async def get_github_repositories(access_token: str) -> list[dict[str, Any]]:
    """Fetch user's GitHub repositories. Used by app/api/projects.py."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    repos: list[dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
        while True:
            resp = await client.get(
                f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated",
                headers=headers,
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
            if len(batch) < 100:
                break
    return repos
