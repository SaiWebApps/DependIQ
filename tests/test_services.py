"""
Unit tests for service modules
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.workos_auth import (
    get_authorization_url,
    verify_session,
)


class TestWorkOSAuthService:
    """Test WorkOS auth service functions"""

    @patch("app.services.workos_auth.get_workos_client")
    def test_get_authorization_url_basic(self, mock_client):
        """Test generating authorization URL without provider."""
        mock_um = MagicMock()
        mock_um.get_authorization_url.return_value = "https://authkit.workos.com/auth"
        mock_client.return_value.user_management = mock_um

        url = get_authorization_url()

        assert url == "https://authkit.workos.com/auth"
        mock_um.get_authorization_url.assert_called_once()

    @patch("app.services.workos_auth.get_workos_client")
    def test_get_authorization_url_with_provider(self, mock_client):
        """Test generating authorization URL with provider."""
        mock_um = MagicMock()
        mock_um.get_authorization_url.return_value = "https://authkit.workos.com/gh"
        mock_client.return_value.user_management = mock_um

        url = get_authorization_url(provider="GitHubOAuth", provider_scopes=["repo"])

        assert "authkit.workos.com" in url
        call_kwargs = mock_um.get_authorization_url.call_args[1]
        assert call_kwargs["provider"] == "GitHubOAuth"
        assert call_kwargs["provider_scopes"] == ["repo"]

    def test_verify_session_valid_jwt(self):
        """Test verifying a valid JWT payload."""
        import jwt as pyjwt

        # Create a test JWT (unsigned, since verify_session uses verify_signature=False)
        payload = {"sub": "user_123", "exp": 9999999999}
        fake_jwt = pyjwt.encode(payload, "unused", algorithm="HS256")

        result = verify_session(fake_jwt)

        assert result is not None
        assert result["sub"] == "user_123"

    def test_verify_session_invalid_jwt(self):
        """Test that invalid JWT returns None."""
        result = verify_session("not.a.jwt")
        assert result is None

    def test_verify_session_empty_string(self):
        """Test that empty string returns None."""
        result = verify_session("")
        assert result is None


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
