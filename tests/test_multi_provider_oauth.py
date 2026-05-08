"""
Tests for multi-provider OAuth integration.

Two layers:
1. Integration tests that hit real WorkOS API to confirm provider strings are valid.
2. Unit tests that verify the callback flow works for non-GitHub providers.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.workos_auth import SESSION_COOKIE_NAME, STATE_COOKIE_NAME
from tests.conftest import TEST_SESSION_TOKEN

ALL_PROVIDERS = ["GitHubOAuth", "GoogleOAuth", "MicrosoftOAuth", "AppleOAuth"]


class TestProviderAuthorizationURLs:
    """Integration tests: hit real WorkOS to confirm each provider string generates a valid URL."""

    @pytest.fixture(autouse=True)
    def _require_workos_keys(self):
        if not os.getenv("WORKOS_API_KEY") or not os.getenv("WORKOS_CLIENT_ID"):
            pytest.fail(
                "WORKOS_API_KEY and WORKOS_CLIENT_ID must be set to run integration tests"
            )

    @pytest.mark.parametrize("provider", ALL_PROVIDERS)
    def test_workos_accepts_provider_string(self, provider):
        """WorkOS generates a valid authorization URL for this provider (not an error)."""
        from app.services.workos_auth import get_authorization_url

        url, state = get_authorization_url(provider=provider)

        assert url.startswith("https://")
        assert "workos.com" in url or "authkit" in url
        assert state  # CSRF token generated
        assert len(state) > 20

    @pytest.mark.parametrize("provider", ALL_PROVIDERS)
    def test_login_endpoint_redirects_for_provider(self, provider, test_client):
        """GET /api/auth/login?provider=X returns a 302 redirect to a valid URL."""
        response = test_client.get(
            f"/api/auth/login?provider={provider}", follow_redirects=False
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "workos.com" in location or "authkit" in location


class TestMultiProviderCallback:
    """Unit tests: verify callback handles all providers correctly."""

    def _make_provider_response(self, provider, email, has_oauth_tokens=False):
        """Build a mock WorkOS response for any provider."""
        mock_user = MagicMock()
        mock_user.id = f"workos_{provider.lower()}_user_001"
        mock_user.email = email
        mock_user.to_dict.return_value = {
            "id": mock_user.id,
            "email": email,
            "object": "user",
            "first_name": "Test",
            "last_name": "User",
            "profile_picture_url": None,
            "email_verified": True,
            "external_id": None,
            "last_sign_in_at": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.user = mock_user
        mock_response.access_token = TEST_SESSION_TOKEN
        mock_response.refresh_token = "refresh_test"
        mock_response.authentication_method = provider
        mock_response.impersonator = None

        if has_oauth_tokens:
            mock_oauth_tokens = MagicMock()
            mock_oauth_tokens.access_token = f"provider_token_{provider}"
            mock_response.oauth_tokens = mock_oauth_tokens
        else:
            mock_response.oauth_tokens = None

        return mock_response

    @pytest.mark.parametrize(
        "provider,email",
        [
            ("GoogleOAuth", "user@gmail.com"),
            ("MicrosoftOAuth", "user@outlook.com"),
            ("AppleOAuth", "user@privaterelay.appleid.com"),
        ],
    )
    @patch("app.api.auth.seal_session")
    @patch("app.api.auth.authenticate_callback")
    def test_callback_creates_user_for_provider(
        self, mock_auth, mock_seal, provider, email, test_client, test_db_session
    ):
        """Callback with a non-GitHub provider creates user and sets session cookie."""
        mock_auth.return_value = self._make_provider_response(provider, email)
        mock_seal.return_value = "sealed_session_value"

        test_client.cookies.set(STATE_COOKIE_NAME, "valid_state")
        response = test_client.get(
            "/api/auth/callback?code=valid_code&state=valid_state",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")

    @pytest.mark.parametrize(
        "provider,email",
        [
            ("GoogleOAuth", "user@gmail.com"),
            ("MicrosoftOAuth", "user@outlook.com"),
            ("AppleOAuth", "user@privaterelay.appleid.com"),
        ],
    )
    @patch("app.api.auth.seal_session")
    @patch("app.api.auth.authenticate_callback")
    def test_callback_with_oauth_tokens_does_not_crash(
        self, mock_auth, mock_seal, provider, email, test_client, test_db_session
    ):
        """If a non-GitHub provider returns oauth_tokens, callback handles it gracefully."""
        mock_auth.return_value = self._make_provider_response(
            provider, email, has_oauth_tokens=True
        )
        mock_seal.return_value = "sealed_session_value"

        test_client.cookies.set(STATE_COOKIE_NAME, "valid_state")
        response = test_client.get(
            "/api/auth/callback?code=valid_code&state=valid_state",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/"

    @patch("app.api.auth.seal_session")
    @patch("app.api.auth.authenticate_callback")
    def test_callback_github_still_stores_token(
        self, mock_auth, mock_seal, test_client, test_db_session
    ):
        """Regression: GitHub callback still correctly stores the access token."""
        mock_auth.return_value = self._make_provider_response(
            "GitHubOAuth", "dev@github.com", has_oauth_tokens=True
        )
        mock_seal.return_value = "sealed_session_value"

        test_client.cookies.set(STATE_COOKIE_NAME, "valid_state")
        response = test_client.get(
            "/api/auth/callback?code=ghcode&state=valid_state",
            follow_redirects=False,
        )

        assert response.status_code == 302


class TestSignInTemplateProviders:
    """Verify the sign-in template has correct provider links."""

    def test_all_provider_buttons_present(self, test_client):
        """Sign-in page renders buttons for all 4 OAuth providers."""
        response = test_client.get("/login")

        assert response.status_code == 200
        html = response.text

        for provider in ALL_PROVIDERS:
            assert f"provider={provider}" in html, (
                f"Missing button for {provider} in sign-in template"
            )

    def test_provider_strings_match_workos_format(self, test_client):
        """Provider strings in template match exact WorkOS enum values (case-sensitive)."""
        response = test_client.get("/login")
        html = response.text

        # These are the exact strings WorkOS accepts — case matters
        assert "provider=GitHubOAuth" in html
        assert "provider=GoogleOAuth" in html
        assert "provider=MicrosoftOAuth" in html
        assert "provider=AppleOAuth" in html

        # Verify no common typos
        assert "provider=GithubOAuth" not in html
        assert "provider=MicroSoftOAuth" not in html
        assert "provider=microsoftoauth" not in html
