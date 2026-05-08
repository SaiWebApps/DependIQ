"""
Tier 2 tests: Auth endpoint behavior — login, callback, logout, cookie attributes.
"""

from unittest.mock import MagicMock, patch

from app.services.workos_auth import SESSION_COOKIE_NAME, STATE_COOKIE_NAME


class TestLoginEndpoint:
    def test_login_redirects_to_workos(self, test_client):
        with patch("app.services.workos_auth.get_workos_client") as mock_client:
            mock_client.return_value.user_management.get_authorization_url.return_value = "https://api.workos.com/user_management/authorize?client_id=test"
            with patch("app.services.workos_auth.validate_workos_config"):
                response = test_client.get("/api/auth/login", follow_redirects=False)

        assert response.status_code == 302
        assert "workos.com" in response.headers["location"]

    def test_login_sets_state_cookie(self, test_client):
        with patch("app.services.workos_auth.get_workos_client") as mock_client:
            mock_client.return_value.user_management.get_authorization_url.return_value = "https://api.workos.com/authorize"
            with patch("app.services.workos_auth.validate_workos_config"):
                response = test_client.get("/api/auth/login", follow_redirects=False)

        cookies = response.headers.get_list("set-cookie")
        state_cookie = [c for c in cookies if STATE_COOKIE_NAME in c]
        assert len(state_cookie) == 1
        assert "httponly" in state_cookie[0].lower()
        assert "path=/" in state_cookie[0].lower()


class TestCallbackEndpoint:
    def test_callback_without_code_redirects(self, test_client):
        response = test_client.get("/api/auth/callback", follow_redirects=False)
        assert response.status_code == 302
        assert "error=no_code" in response.headers["location"]

    def test_callback_with_error_redirects(self, test_client):
        response = test_client.get(
            "/api/auth/callback?error=access_denied", follow_redirects=False
        )
        assert response.status_code == 302
        assert "error=auth_denied" in response.headers["location"]

    def test_callback_without_matching_state_rejects(self, test_client):
        response = test_client.get(
            "/api/auth/callback?code=valid_code&state=attacker_state",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "error=invalid_state" in response.headers["location"]

    def test_callback_with_valid_state_sets_session_cookie(
        self, test_client, test_user
    ):
        mock_auth_response = MagicMock()
        mock_auth_response.user.id = test_user.workos_user_id
        mock_auth_response.user.email = test_user.email
        mock_auth_response.access_token = "at_test"
        mock_auth_response.refresh_token = "rt_test"
        mock_auth_response.impersonator = None
        mock_auth_response.oauth_tokens = None
        mock_auth_response.authentication_method = None

        with (
            patch(
                "app.api.auth.authenticate_callback", return_value=mock_auth_response
            ),
            patch("app.api.auth.seal_session", return_value="sealed_cookie_value"),
        ):
            test_client.cookies.set(STATE_COOKIE_NAME, "valid_state_token")
            response = test_client.get(
                "/api/auth/callback?code=auth_code_123&state=valid_state_token",
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert response.headers["location"] == "/"

        cookies = response.headers.get_list("set-cookie")
        session_cookies = [c for c in cookies if SESSION_COOKIE_NAME in c]
        assert len(session_cookies) >= 1

        session_cookie = session_cookies[0]
        assert "path=/" in session_cookie.lower()
        assert "httponly" in session_cookie.lower()
        assert "samesite=lax" in session_cookie.lower()


class TestLogoutEndpoint:
    def test_logout_clears_cookie(self, test_client):
        response = test_client.post("/api/auth/logout")
        assert response.status_code == 200

        cookies = response.headers.get_list("set-cookie")
        delete_cookies = [c for c in cookies if SESSION_COOKIE_NAME in c]
        assert len(delete_cookies) >= 1
        assert "path=/" in delete_cookies[0].lower()


class TestMeEndpoint:
    def test_me_without_cookie_returns_401(self, test_client):
        with patch(
            "app.services.workos_auth.verify_or_refresh_session",
            return_value=(None, None),
        ):
            response = test_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_valid_session_returns_user(self, test_client, auth_headers):
        response = test_client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data


class TestPageAuthRedirect:
    def test_home_without_cookie_redirects_to_login(self, test_client):
        with patch(
            "app.services.workos_auth.verify_or_refresh_session",
            return_value=(None, None),
        ):
            response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]
