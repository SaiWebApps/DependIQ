"""
Unit tests for service modules
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import jwt
import pytest

from app.config import Config
from app.services.token_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_id_from_token,
    verify_token,
)


class TestTokenService:
    """Test token service functions"""

    def test_create_access_token(self):
        """Test creating an access token"""
        user_id = "user123"
        email = "test@example.com"

        token = create_access_token(user_id, email)

        assert token is not None
        assert isinstance(token, str)

        # Decode to verify contents
        payload = jwt.decode(
            token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM]
        )

        assert payload["sub"] == user_id
        assert payload["email"] == email
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_refresh_token(self):
        """Test creating a refresh token"""
        user_id = "user123"

        token = create_refresh_token(user_id)

        assert token is not None
        assert isinstance(token, str)

        # Decode to verify contents
        payload = jwt.decode(
            token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM]
        )

        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_verify_token_valid_access(self):
        """Test verifying valid access token"""
        user_id = "user123"
        email = "test@example.com"

        token = create_access_token(user_id, email)
        payload = verify_token(token, "access")

        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["email"] == email

    def test_verify_token_valid_refresh(self):
        """Test verifying valid refresh token"""
        user_id = "user123"

        token = create_refresh_token(user_id)
        payload = verify_token(token, "refresh")

        assert payload is not None
        assert payload["sub"] == user_id

    def test_verify_token_wrong_type(self):
        """Test verifying token with wrong type"""
        user_id = "user123"

        # Create access token but try to verify as refresh
        token = create_access_token(user_id, "test@example.com")
        payload = verify_token(token, "refresh")

        assert payload is None

    def test_verify_token_invalid(self):
        """Test verifying invalid token"""
        payload = verify_token("invalid.token.here", "access")
        assert payload is None

    def test_verify_token_expired(self):
        """Test verifying expired token"""
        # Create token that expires immediately
        expire = datetime.utcnow() - timedelta(minutes=1)
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }

        token = jwt.encode(
            payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM
        )

        result = verify_token(token, "access")
        assert result is None

    def test_decode_token(self):
        """Test decoding token without verification"""
        user_id = "user123"
        email = "test@example.com"

        token = create_access_token(user_id, email)
        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == user_id

    def test_decode_token_invalid(self):
        """Test decoding invalid token"""
        payload = decode_token("completely.invalid.token")
        assert payload is None

    def test_get_user_id_from_token(self):
        """Test extracting user ID from token"""
        user_id = "user123"
        email = "test@example.com"

        token = create_access_token(user_id, email)
        extracted_id = get_user_id_from_token(token)

        assert extracted_id == user_id

    def test_get_user_id_from_invalid_token(self):
        """Test extracting user ID from invalid token"""
        user_id = get_user_id_from_token("invalid.token")
        assert user_id is None

    def test_token_expiration_times(self):
        """Test that tokens have correct expiration times"""
        user_id = "user123"

        # Access token
        access_token = create_access_token(user_id, "test@example.com")
        access_payload = decode_token(access_token)
        assert access_payload is not None
        access_exp = datetime.fromtimestamp(access_payload["exp"])
        access_iat = datetime.fromtimestamp(access_payload["iat"])
        access_lifetime = (access_exp - access_iat).total_seconds() / 60

        # Should be approximately the configured minutes
        assert abs(access_lifetime - Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES) < 1

        # Refresh token
        refresh_token = create_refresh_token(user_id)
        refresh_payload = decode_token(refresh_token)
        assert refresh_payload is not None
        refresh_exp = datetime.fromtimestamp(refresh_payload["exp"])
        refresh_iat = datetime.fromtimestamp(refresh_payload["iat"])
        refresh_lifetime = (refresh_exp - refresh_iat).total_seconds() / (60 * 60 * 24)

        # Should be approximately the configured days
        assert abs(refresh_lifetime - Config.JWT_REFRESH_TOKEN_EXPIRE_DAYS) < 1


class TestGitHubOAuthService:
    """Test GitHub OAuth service"""

    @pytest.mark.asyncio
    async def test_get_authorize_url(self, test_db_session):
        """Test generating GitHub authorization URL"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)
        state = "random_state_string"

        url = service.get_authorize_url(state)

        assert "github.com/login/oauth/authorize" in url
        assert f"state={state}" in url
        assert "client_id=" in url
        assert "scope=" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, test_db_session):
        """Test successful token exchange"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "gho_test_token",
                "token_type": "bearer",
            }

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await service.exchange_code_for_token("test_code")

            assert result == "gho_test_token"

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self, test_db_session):
        """Test failed token exchange returns None"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"error": "bad_verification_code"}

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await service.exchange_code_for_token("bad_code")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_github_user_success(self, test_db_session):
        """Test getting GitHub user info"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)

        mock_user_data = {"id": 12345, "login": "testuser", "email": "test@example.com"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_user_data

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await service.get_github_user("test_token")

            assert result is not None
            assert result["id"] == 12345
            assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_github_user_no_email_fetches_emails(self, test_db_session):
        """Test fetching emails endpoint when user has no public email"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)

        mock_user_data = {"id": 12345, "login": "testuser", "email": None}
        mock_emails_data = [
            {"email": "primary@example.com", "primary": True, "verified": True}
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_user_response = Mock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = mock_user_data

            mock_emails_response = Mock()
            mock_emails_response.status_code = 200
            mock_emails_response.json.return_value = mock_emails_data

            async def mock_get(url, **kwargs):
                if "user/emails" in url:
                    return mock_emails_response
                return mock_user_response

            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await service.get_github_user("test_token")

            assert result is not None
            assert result["email"] == "primary@example.com"

    @pytest.mark.asyncio
    async def test_get_or_create_user_new(self, test_db_session):
        """Test creating a new user from GitHub data"""
        from app.services.github_oauth_service import GitHubOAuthService

        service = GitHubOAuthService(test_db_session)

        github_user = {
            "id": 99999,
            "login": "newuser",
            "email": "new@example.com",
        }

        user = await service.get_or_create_user(github_user, "access_token_123")

        assert user is not None
        assert user.email == "new@example.com"
        assert user.email_verified is True
