"""
GitHub OAuth service for handling authentication flow
"""

import secrets
import urllib.parse

import requests
from authlib.common.errors import AuthlibBaseError

from ..config import Config


class GitHubOAuthService:
    """Service for handling GitHub OAuth authentication"""

    def __init__(self):
        self.client_id = Config.GITHUB_CLIENT_ID
        self.client_secret = Config.GITHUB_CLIENT_SECRET
        self.redirect_uri = Config.GITHUB_REDIRECT_URI
        self.scope = Config.GITHUB_OAUTH_SCOPES

    def _check_credentials(self):
        """Check if OAuth credentials are configured"""
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "GitHub OAuth credentials not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables."
            )

    def generate_state(self) -> str:
        """Generate a secure random state parameter for OAuth flow"""
        return secrets.token_urlsafe(32)

    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub OAuth authorization URL"""
        self._check_credentials()
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
            "response_type": "code",
        }

        query_string = urllib.parse.urlencode(params)
        return f"https://github.com/login/oauth/authorize?{query_string}"

    def exchange_code_for_token(self, code: str, state: str) -> dict:
        """Exchange authorization code for access token"""
        self._check_credentials()
        try:
            token_url = "https://github.com/login/oauth/access_token"

            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }

            headers = {"Accept": "application/json", "User-Agent": "dependiq-App/1.0"}

            response = requests.post(token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()

            token_data = response.json()

            if "error" in token_data:
                raise AuthlibBaseError(
                    f"OAuth error: {token_data.get('error_description', token_data['error'])}"
                )

            return token_data

        except requests.exceptions.RequestException as e:
            raise AuthlibBaseError(f"Network error during token exchange: {e!s}")
        except Exception as e:
            raise AuthlibBaseError(f"Unexpected error during token exchange: {e!s}")

    def get_user_info(self, access_token: str) -> dict:
        """Get user information from GitHub API"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "dependiq-App/1.0",
            }

            # Get user basic info
            user_response = requests.get(
                f"{Config.GITHUB_API_BASE}/user", headers=headers, timeout=10
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            # Get user email addresses
            email_response = requests.get(
                f"{Config.GITHUB_API_BASE}/user/emails", headers=headers, timeout=10
            )
            email_response.raise_for_status()
            emails = email_response.json()

            # Find primary email
            primary_email = None
            for email in emails:
                if email.get("primary", False):
                    primary_email = email["email"]
                    break

            # Combine user data with primary email
            user_data["primary_email"] = primary_email

            return user_data

        except requests.exceptions.RequestException as e:
            raise AuthlibBaseError(f"Network error while fetching user info: {e!s}")
        except Exception as e:
            raise AuthlibBaseError(f"Unexpected error while fetching user info: {e!s}")

    def validate_token(self, access_token: str) -> bool:
        """Validate if the access token is still valid"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "dependiq-App/1.0",
            }

            response = requests.get(
                f"{Config.GITHUB_API_BASE}/user", headers=headers, timeout=5
            )

            return response.status_code == 200

        except Exception:
            return False
