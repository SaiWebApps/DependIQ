"""
Integration tests for password reset flow, logout, and expired JWT handling
"""

import asyncio
import secrets as stdlib_secrets
from datetime import datetime, timedelta

import jwt
from fastapi import status
from sqlalchemy import select

from app.config import Config
from app.models import PasswordResetToken


def _make_expired_access_token(user_id: str, email: str) -> str:
    """Create a properly signed but expired access token for testing."""
    signing_key = Config.JWT_SECRET_KEY
    algo = Config.JWT_ALGORITHM
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() - timedelta(hours=1),
        "iat": datetime.utcnow() - timedelta(hours=2),
        "type": "access",
    }
    return jwt.encode(payload, signing_key, algorithm=algo)


def _make_refresh_type_token(user_id: str) -> str:
    """Create a refresh-type token (should not work as access token)."""
    signing_key = Config.JWT_SECRET_KEY
    algo = Config.JWT_ALGORITHM
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow(),
        "type": "refresh",
    }
    return jwt.encode(payload, signing_key, algorithm=algo)


class TestForgotPassword:
    """Test forgot-password endpoint (POST /api/auth/forgot-password)"""

    def test_forgot_password_valid_email(self, test_client, test_user):
        """Test forgot-password with a registered email returns success"""
        response = test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "if an account exists" in data["message"].lower()

    def test_forgot_password_nonexistent_email(self, test_client):
        """Test forgot-password with non-existent email still returns success (anti-enumeration)"""
        response = test_client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Must return same message as valid email to prevent enumeration
        assert "if an account exists" in data["message"].lower()

    def test_forgot_password_creates_reset_token(
        self, test_client, test_user, test_db_session
    ):
        """Test that forgot-password creates a PasswordResetToken in the database"""
        response = test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify token was created in the database
        async def check_token():
            result = await test_db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == test_user.id
                )
            )
            return result.scalar_one_or_none()

        token = asyncio.run(check_token())
        assert token is not None
        assert token.used_at is None
        assert token.expires_at > datetime.utcnow()

    def test_forgot_password_invalid_email_format(self, test_client):
        """Test forgot-password with invalid email format returns 422"""
        response = test_client.post(
            "/api/auth/forgot-password", json={"email": "not-an-email"}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestResetPassword:
    """Test reset-password endpoint (POST /api/auth/reset-password)"""

    def test_reset_password_valid_token(self, test_client, test_user, test_db_session):
        """Test successful password reset with valid token"""
        # Request a password reset to generate a token
        test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )

        # Retrieve the token from the database
        async def get_token():
            result = await test_db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == test_user.id
                )
            )
            return result.scalar_one_or_none()

        reset_token = asyncio.run(get_token())
        assert reset_token is not None

        # Reset the password
        new_password = "NewSecurePass456!"
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": reset_token.token,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert "reset successfully" in response.json()["message"].lower()

        # Verify login with new password works
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": new_password},
        )
        assert login_response.status_code == status.HTTP_200_OK

    def test_reset_password_invalid_token(self, test_client):
        """Test reset-password with a token that does not exist in the database"""
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": "completely_invalid_token_that_does_not_exist",
                "new_password": "NewSecurePass456!",
                "confirm_password": "NewSecurePass456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid" in response.json()["detail"].lower()

    def test_reset_password_expired_token(self, test_client, test_user, test_db_session):
        """Test reset-password with an expired token"""
        # Manually create an expired token in the database
        expired_token = PasswordResetToken(
            user_id=test_user.id,
            token=stdlib_secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() - timedelta(hours=2),  # Expired 2 hours ago
        )

        async def insert_token():
            test_db_session.add(expired_token)
            await test_db_session.commit()
            await test_db_session.refresh(expired_token)

        asyncio.run(insert_token())

        # Attempt reset with the expired token
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": expired_token.token,
                "new_password": "NewSecurePass456!",
                "confirm_password": "NewSecurePass456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in response.json()["detail"].lower()

    def test_reset_password_already_used_token(
        self, test_client, test_user, test_db_session
    ):
        """Test reset-password with a token that has already been consumed"""
        # Create a used token
        used_token = PasswordResetToken(
            user_id=test_user.id,
            token=stdlib_secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            used_at=datetime.utcnow() - timedelta(minutes=30),  # Used 30 min ago
        )

        async def insert_token():
            test_db_session.add(used_token)
            await test_db_session.commit()
            await test_db_session.refresh(used_token)

        asyncio.run(insert_token())

        # Attempt reset with the already-used token
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": used_token.token,
                "new_password": "NewSecurePass456!",
                "confirm_password": "NewSecurePass456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been used" in response.json()["detail"].lower()

    def test_reset_password_weak_password(
        self, test_client, test_user, test_db_session
    ):
        """Test reset-password rejects a weak new password"""
        # Request a password reset
        test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )

        async def get_token():
            result = await test_db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == test_user.id
                )
            )
            return result.scalar_one_or_none()

        reset_token = asyncio.run(get_token())
        assert reset_token is not None

        # Attempt reset with a weak password
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": reset_token.token,
                "new_password": "weak",
                "confirm_password": "weak",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.json()["detail"].lower()

    def test_reset_password_mismatched_passwords(
        self, test_client, test_user, test_db_session
    ):
        """Test reset-password rejects mismatched new_password and confirm_password"""
        # Request a password reset
        test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )

        async def get_token():
            result = await test_db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == test_user.id
                )
            )
            return result.scalar_one_or_none()

        reset_token = asyncio.run(get_token())
        assert reset_token is not None

        # Attempt reset with mismatched passwords
        response = test_client.post(
            "/api/auth/reset-password",
            json={
                "token": reset_token.token,
                "new_password": "StrongPass123!",
                "confirm_password": "DifferentPass456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "do not match" in response.json()["detail"].lower()

    def test_reset_password_old_password_no_longer_works(
        self, test_client, test_user, test_db_session
    ):
        """Test that after reset, the old password no longer works"""
        # Request a password reset
        test_client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )

        async def get_token():
            result = await test_db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == test_user.id
                )
            )
            return result.scalar_one_or_none()

        reset_token = asyncio.run(get_token())

        # Reset the password
        new_password = "BrandNewPass789!"
        test_client.post(
            "/api/auth/reset-password",
            json={
                "token": reset_token.token,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )

        # Old password should fail
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )
        assert login_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogout:
    """Test logout endpoint (POST /api/auth/logout)"""

    def test_logout_authenticated_user(self, test_client, auth_headers):
        """Test successful logout with valid authentication"""
        response = test_client.post("/api/auth/logout", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert "logged out" in response.json()["message"].lower()

    def test_logout_unauthenticated(self, test_client):
        """Test logout without authentication returns 401"""
        response = test_client.post("/api/auth/logout")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_invalid_token(self, test_client):
        """Test logout with an invalid token returns 401"""
        response = test_client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer invalid.token.string"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestExpiredJWT:
    """Test protected route behavior with expired JWT tokens"""

    def test_expired_access_token_rejected(self, test_client, test_user):
        """Test that a real expired JWT token is rejected by protected routes"""
        expired_token = _make_expired_access_token(
            str(test_user.id), test_user.email
        )

        # Attempt to access a protected endpoint
        response = test_client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_expired_token_differs_from_invalid_token(self, test_client, test_user):
        """Test that both expired and garbage tokens get 401 (no information leak)"""
        expired_token = _make_expired_access_token(
            str(test_user.id), test_user.email
        )

        # Both should get the same status code (no enumeration)
        expired_response = test_client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        garbage_response = test_client.get(
            "/api/user/profile",
            headers={"Authorization": "Bearer totally.garbage.token"},
        )

        assert expired_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert garbage_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_expired_token_on_logout(self, test_client, test_user):
        """Test that logout also rejects expired tokens"""
        expired_token = _make_expired_access_token(
            str(test_user.id), test_user.email
        )

        response = test_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_token_type_rejected(self, test_client, test_user):
        """Test that a refresh token cannot be used as an access token"""
        refresh_token = _make_refresh_type_token(str(test_user.id))

        response = test_client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
