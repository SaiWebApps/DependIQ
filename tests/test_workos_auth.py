"""
Tests for WorkOS AuthKit authentication flow.

Mocks the WorkOS SDK responses to test callback, session, and logout flows.
"""

import os
from unittest.mock import MagicMock, patch

from fastapi import status

from tests.conftest import TEST_SESSION_TOKEN, TEST_WORKOS_USER_ID

# Test values sourced from env (see conftest.py)
MOCK_JWT = os.getenv("TEST_SESSION_TOKEN", "placeholder")
MOCK_GH = os.getenv("TEST_GITHUB_TOKEN", "placeholder")


def _make_workos_response(user_id, email, jwt_val=None, gh_val=None, method=None):
    """Build a mock WorkOS authenticate_with_code response."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email

    mock_response = MagicMock()
    mock_response.user = mock_user
    mock_response.configure_mock(**{"access_token": jwt_val or MOCK_JWT})
    mock_response.authentication_method = method

    if gh_val:
        mock_oauth_tokens = MagicMock()
        mock_oauth_tokens.configure_mock(**{"access_token": gh_val})
        mock_response.oauth_tokens = mock_oauth_tokens
    else:
        mock_response.oauth_tokens = None

    return mock_response


class TestAuthCallback:
    """Test the /api/auth/callback endpoint."""

    def test_callback_without_code_redirects_to_login(self, test_client):
        """Missing code param should redirect to login with error."""
        response = test_client.get("/api/auth/callback", follow_redirects=False)
        assert response.status_code == 302
        assert "/login?error=no_code" in response.headers["location"]

    def test_callback_with_error_redirects_to_login(self, test_client):
        """OAuth error should redirect to login."""
        response = test_client.get(
            "/api/auth/callback?error=access_denied", follow_redirects=False
        )
        assert response.status_code == 302
        assert "/login?error=auth_denied" in response.headers["location"]

    @patch("app.api.auth.authenticate_callback")
    def test_callback_with_valid_code_sets_cookie(
        self, mock_auth, test_client, test_db_session
    ):
        """Valid code should create user, set cookie, redirect to /."""
        mock_auth.return_value = _make_workos_response(
            "workos_new_id", "newuser@example.com"
        )

        response = test_client.get(
            "/api/auth/callback?code=valid", follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert "dependiq_session" in response.headers.get("set-cookie", "")

    @patch("app.api.auth.authenticate_callback")
    def test_callback_stores_github_provider_info(
        self, mock_auth, test_client, test_db_session
    ):
        """Callback with GitHub OAuth tokens should store the token on user."""
        mock_auth.return_value = _make_workos_response(
            "workos_gh_id",
            "githubuser@example.com",
            gh_val=MOCK_GH,
            method="GitHubOAuth",
        )

        response = test_client.get(
            "/api/auth/callback?code=ghcode", follow_redirects=False
        )

        assert response.status_code == 302

    @patch("app.api.auth.authenticate_callback")
    def test_callback_with_invalid_code_redirects_error(
        self, mock_auth, test_client
    ):
        """Invalid code should redirect to login with error."""
        mock_auth.side_effect = Exception("Invalid code")

        response = test_client.get(
            "/api/auth/callback?code=bad", follow_redirects=False
        )

        assert response.status_code == 302
        assert "/login?error=auth_failed" in response.headers["location"]


class TestLogout:
    """Test the POST /api/auth/logout endpoint."""

    def test_logout_clears_cookie(self, test_client):
        """Logout should clear the session cookie."""
        response = test_client.post("/api/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

        # Check cookie deletion header
        set_cookie = response.headers.get("set-cookie", "")
        assert "dependiq_session" in set_cookie


class TestProtectedRoutes:
    """Test that protected routes require authentication."""

    def test_api_me_without_cookie_returns_401(self, test_client):
        """GET /api/auth/me without session cookie should return 401."""
        response = test_client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("app.services.workos_auth.verify_session")
    def test_api_me_with_valid_cookie_returns_user(
        self, mock_verify, test_client, test_user
    ):
        """GET /api/auth/me with valid session should return user info."""
        mock_verify.return_value = {"sub": TEST_WORKOS_USER_ID}

        response = test_client.get(
            "/api/auth/me",
            cookies={"dependiq_session": TEST_SESSION_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"

    def test_home_without_cookie_redirects_to_login(self, test_client):
        """GET / without session should redirect to /login."""
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    @patch("app.services.workos_auth.verify_session")
    def test_home_with_valid_cookie_returns_200(
        self, mock_verify, test_client, test_user
    ):
        """GET / with valid session should return 200."""
        mock_verify.return_value = {"sub": TEST_WORKOS_USER_ID}

        response = test_client.get(
            "/",
            cookies={"dependiq_session": TEST_SESSION_TOKEN},
        )

        assert response.status_code == 200


class TestLoginRedirect:
    """Test the GET /api/auth/login endpoint."""

    @patch("app.api.auth.get_authorization_url")
    def test_login_redirects_to_workos(self, mock_url, test_client):
        """GET /api/auth/login should redirect to WorkOS."""
        mock_url.return_value = "https://authkit.workos.com/authorize?id=test"

        response = test_client.get("/api/auth/login", follow_redirects=False)

        assert response.status_code == 302
        assert "authkit.workos.com" in response.headers["location"]

    @patch("app.api.auth.get_authorization_url")
    def test_login_with_provider_passes_provider(self, mock_url, test_client):
        """GET /api/auth/login?provider=GitHubOAuth should pass provider."""
        mock_url.return_value = "https://authkit.workos.com/authorize?p=github"

        response = test_client.get(
            "/api/auth/login?provider=GitHubOAuth&scope=repo",
            follow_redirects=False,
        )

        assert response.status_code == 302
        mock_url.assert_called_once_with(
            provider="GitHubOAuth",
            provider_scopes=["repo"],
        )
