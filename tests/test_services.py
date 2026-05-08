"""
Unit tests for service modules
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.workos_auth import (
    get_authorization_url,
    verify_or_refresh_session,
)


class TestWorkOSAuthService:
    """Test WorkOS auth service functions"""

    @patch("app.services.workos_auth.get_workos_client")
    def test_get_authorization_url_basic(self, mock_client):
        """Test generating authorization URL without provider."""
        mock_um = MagicMock()
        mock_um.get_authorization_url.return_value = "https://authkit.workos.com/auth"
        mock_client.return_value.user_management = mock_um

        url, state = get_authorization_url()

        assert url == "https://authkit.workos.com/auth"
        assert len(state) > 20
        mock_um.get_authorization_url.assert_called_once()

    @patch("app.services.workos_auth.get_workos_client")
    def test_get_authorization_url_with_provider(self, mock_client):
        """Test generating authorization URL with provider."""
        mock_um = MagicMock()
        mock_um.get_authorization_url.return_value = "https://authkit.workos.com/gh"
        mock_client.return_value.user_management = mock_um

        url, state = get_authorization_url(provider="GitHubOAuth", provider_scopes=["repo"])

        assert "authkit.workos.com" in url
        assert len(state) > 20
        call_kwargs = mock_um.get_authorization_url.call_args[1]
        assert call_kwargs["provider"] == "GitHubOAuth"
        assert call_kwargs["provider_scopes"] == ["repo"]
        assert "state" in call_kwargs

    @patch("app.services.workos_auth.get_workos_client")
    def test_verify_session_valid_sealed_cookie(self, mock_get_client):
        """Test verifying a valid sealed session cookie."""
        from workos.session import AuthenticateWithSessionCookieSuccessResponse

        mock_session = MagicMock()
        mock_session.authenticate.return_value = (
            AuthenticateWithSessionCookieSuccessResponse(
                authenticated=True,
                session_id="sess_123",
                user={"id": "user_123", "email": "test@example.com"},
            )
        )
        mock_um = MagicMock()
        mock_um.load_sealed_session.return_value = mock_session
        mock_get_client.return_value.user_management = mock_um

        result, new_cookie = verify_or_refresh_session("sealed_data_here")

        assert result is not None
        assert result.authenticated is True
        assert result.user["id"] == "user_123"
        assert new_cookie is None

    @patch("app.services.workos_auth.get_workos_client")
    def test_verify_session_invalid_sealed_cookie(self, mock_get_client):
        """Test that invalid sealed cookie returns None."""
        from workos.session import (
            AuthenticateWithSessionCookieErrorResponse,
            AuthenticateWithSessionCookieFailureReason,
        )

        mock_session = MagicMock()
        mock_session.authenticate.return_value = (
            AuthenticateWithSessionCookieErrorResponse(
                authenticated=False,
                reason=AuthenticateWithSessionCookieFailureReason.INVALID_SESSION_COOKIE,
            )
        )
        mock_um = MagicMock()
        mock_um.load_sealed_session.return_value = mock_session
        mock_get_client.return_value.user_management = mock_um

        result, new_cookie = verify_or_refresh_session("bad_sealed_data")
        assert result is None
        assert new_cookie is None

    @patch("app.services.workos_auth.get_workos_client")
    def test_verify_session_expired_triggers_refresh(self, mock_get_client):
        """Test that expired JWT triggers refresh attempt."""
        from workos.session import (
            AuthenticateWithSessionCookieErrorResponse,
            AuthenticateWithSessionCookieFailureReason,
            RefreshWithSessionCookieSuccessResponse,
        )

        mock_session = MagicMock()
        mock_session.authenticate.return_value = (
            AuthenticateWithSessionCookieErrorResponse(
                authenticated=False,
                reason=AuthenticateWithSessionCookieFailureReason.INVALID_JWT,
            )
        )
        mock_session.refresh.return_value = RefreshWithSessionCookieSuccessResponse(
            authenticated=True,
            sealed_session="new_sealed_cookie",
            session_id="sess_refreshed",
            user={"id": "user_123", "email": "test@example.com"},
        )
        mock_um = MagicMock()
        mock_um.load_sealed_session.return_value = mock_session
        mock_get_client.return_value.user_management = mock_um

        result, new_cookie = verify_or_refresh_session("expired_sealed_data")
        assert result is not None
        assert result.authenticated is True
        assert new_cookie == "new_sealed_cookie"


class TestGitHubRepositories:
    """Test GitHub repository fetching"""

    @pytest.mark.asyncio
    async def test_get_github_repositories_success(self):
        """Test successful repository fetch."""
        from app.services.github_oauth_service import get_github_repositories

        mock_repos = [{"name": "repo1", "full_name": "user/repo1"}]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_repos

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            repos = await get_github_repositories("some_val")

            assert len(repos) == 1
            assert repos[0]["name"] == "repo1"

    @pytest.mark.asyncio
    async def test_get_github_repositories_failure(self):
        """Test failed repository fetch returns empty list."""
        from app.services.github_oauth_service import get_github_repositories

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"message": "Bad credentials"}

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            repos = await get_github_repositories("bad_val")

            assert repos == []
