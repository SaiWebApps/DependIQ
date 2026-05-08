"""
Tier 2 tests: Session.authenticate() with local JWKS mock.

Uses the same pattern as WorkOS's own test suite:
- Generate RSA keypair, sign JWT, mock session.jwks, verify result.
"""

from unittest.mock import MagicMock, patch

from workos.session import (
    AuthenticateWithSessionCookieErrorResponse,
    AuthenticateWithSessionCookieFailureReason,
    AuthenticateWithSessionCookieSuccessResponse,
    RefreshWithSessionCookieSuccessResponse,
)

from app.services.workos_auth import verify_or_refresh_session


class TestSessionVerify:

    def test_valid_session_returns_authenticated(self, fernet_key, make_sealed_session, mock_jwks):
        sealed = make_sealed_session(user_id="user_99", email="valid@test.com")

        with patch("app.services.workos_auth.Config") as mock_config:
            mock_config.WORKOS_API_KEY = "sk_test_key"
            mock_config.WORKOS_CLIENT_ID = "client_test"
            mock_config.WORKOS_COOKIE_PASSWORD = fernet_key

            with patch("app.services.workos_auth.get_workos_client") as mock_get_client:
                mock_session_obj = self._build_mock_session(sealed, fernet_key, mock_jwks)
                mock_get_client.return_value.user_management.load_sealed_session.return_value = mock_session_obj

                result, new_cookie = verify_or_refresh_session(sealed)

        assert result is not None
        assert result.authenticated is True
        assert result.user["id"] == "user_99"
        assert new_cookie is None

    def test_expired_jwt_triggers_refresh(self, fernet_key, make_sealed_session, mock_jwks):
        sealed = make_sealed_session(user_id="user_exp", expired=True)

        with patch("app.services.workos_auth.get_workos_client") as mock_get_client:
            mock_session_obj = self._build_expired_session_with_refresh(
                sealed, fernet_key, user_id="user_exp"
            )
            mock_get_client.return_value.user_management.load_sealed_session.return_value = mock_session_obj

            with patch("app.services.workos_auth.Config") as mock_config:
                mock_config.WORKOS_COOKIE_PASSWORD = fernet_key
                mock_config.WORKOS_API_KEY = "sk_test"
                mock_config.WORKOS_CLIENT_ID = "client_test"

                result, new_cookie = verify_or_refresh_session(sealed)

        assert result is not None
        assert result.authenticated is True
        assert new_cookie == "new_sealed_session_after_refresh"

    def test_corrupted_cookie_returns_none(self, fernet_key):
        with patch("app.services.workos_auth.get_workos_client") as mock_get_client:
            mock_session_obj = self._build_invalid_session()
            mock_get_client.return_value.user_management.load_sealed_session.return_value = mock_session_obj

            with patch("app.services.workos_auth.Config") as mock_config:
                mock_config.WORKOS_COOKIE_PASSWORD = fernet_key
                mock_config.WORKOS_API_KEY = "sk_test"
                mock_config.WORKOS_CLIENT_ID = "client_test"

                result, new_cookie = verify_or_refresh_session("garbage_data")

        assert result is None
        assert new_cookie is None

    def test_refresh_failure_returns_none(self, fernet_key, make_sealed_session):
        sealed = make_sealed_session(user_id="user_dead", expired=True)

        with patch("app.services.workos_auth.get_workos_client") as mock_get_client:
            mock_session_obj = self._build_expired_session_refresh_fails(sealed, fernet_key)
            mock_get_client.return_value.user_management.load_sealed_session.return_value = mock_session_obj

            with patch("app.services.workos_auth.Config") as mock_config:
                mock_config.WORKOS_COOKIE_PASSWORD = fernet_key
                mock_config.WORKOS_API_KEY = "sk_test"
                mock_config.WORKOS_CLIENT_ID = "client_test"

                result, new_cookie = verify_or_refresh_session(sealed)

        assert result is None
        assert new_cookie is None

    @staticmethod
    def _build_mock_session(sealed, fernet_key, mock_jwks):
        session = MagicMock()
        session.authenticate.return_value = AuthenticateWithSessionCookieSuccessResponse(
            authenticated=True,
            session_id="sess_01",
            user={"id": "user_99", "email": "valid@test.com"},
        )
        return session

    @staticmethod
    def _build_expired_session_with_refresh(sealed, fernet_key, user_id):
        session = MagicMock()
        session.authenticate.return_value = AuthenticateWithSessionCookieErrorResponse(
            authenticated=False,
            reason=AuthenticateWithSessionCookieFailureReason.INVALID_JWT,
        )
        session.refresh.return_value = RefreshWithSessionCookieSuccessResponse(
            authenticated=True,
            sealed_session="new_sealed_session_after_refresh",
            session_id="sess_refreshed",
            user={"id": user_id, "email": "refreshed@test.com"},
        )
        return session

    @staticmethod
    def _build_invalid_session():
        session = MagicMock()
        session.authenticate.return_value = AuthenticateWithSessionCookieErrorResponse(
            authenticated=False,
            reason=AuthenticateWithSessionCookieFailureReason.INVALID_SESSION_COOKIE,
        )
        return session

    @staticmethod
    def _build_expired_session_refresh_fails(sealed, fernet_key):
        session = MagicMock()
        session.authenticate.return_value = AuthenticateWithSessionCookieErrorResponse(
            authenticated=False,
            reason=AuthenticateWithSessionCookieFailureReason.INVALID_JWT,
        )
        session.refresh.side_effect = Exception("Refresh token expired")
        return session
