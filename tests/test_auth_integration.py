"""
Integration tests for authentication flow
"""

from fastapi import status


class TestUserRegistration:
    """Test user registration flow"""

    def test_register_valid_user(self, test_client, valid_user_data):
        """Test successful user registration"""
        response = test_client.post("/api/auth/register", json=valid_user_data)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == valid_user_data["email"]
        assert "password" not in data["user"]  # Password should not be returned

    def test_register_duplicate_email(self, test_client, valid_user_data, test_user):
        """Test registration with existing email"""
        duplicate_data = {
            "email": "test@example.com",  # Same as test_user
            "password": "ValidPass123!",
            "confirm_password": "ValidPass123!",
        }

        response = test_client.post("/api/auth/register", json=duplicate_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"].lower()

    def test_register_password_mismatch(self, test_client, invalid_user_data):
        """Test registration with mismatched passwords"""
        response = test_client.post("/api/auth/register", json=invalid_user_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "do not match" in response.json()["detail"].lower()

    def test_register_weak_password(self, test_client, weak_password):
        """Test registration with weak password"""
        data = {
            "email": "weakpass@example.com",
            "password": weak_password,
            "confirm_password": weak_password,
        }

        response = test_client.post("/api/auth/register", json=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.json()["detail"].lower()

    def test_register_invalid_email(self, test_client, test_password):
        """Test registration with invalid email format"""
        data = {
            "email": "not-an-email",
            "password": test_password,
            "confirm_password": test_password,
        }

        response = test_client.post("/api/auth/register", json=data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUserLogin:
    """Test user login flow"""

    def test_login_valid_credentials(self, test_client, test_user):
        """Test successful login with valid credentials"""
        response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_email(self, test_client):
        """Test login with non-existent email"""
        response = test_client.post(
            "/api/auth/login",
            json={"email": "nonexistent@example.com", "password": "SomePassword123!"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid" in response.json()["detail"].lower()

    def test_login_invalid_password(self, test_client, test_user):
        """Test login with incorrect password"""
        response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPassword123!"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid" in response.json()["detail"].lower()

    def test_login_unverified_email(self, test_client, test_user_unverified):
        """Test login with unverified email"""
        response = test_client.post(
            "/api/auth/login",
            json={"email": "unverified@example.com", "password": "TestPassword123!"},
        )

        # Should still allow login but might show verification warning
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]


class TestTokenRefresh:
    """Test token refresh flow"""

    def test_refresh_valid_token(self, test_client, test_user):
        """Test refreshing access token with valid refresh token"""
        # First login to get tokens
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Refresh the token
        response = test_client.post(
            "/api/auth/refresh", json={"refresh_token": refresh_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_invalid_token(self, test_client):
        """Test refreshing with invalid token"""
        response = test_client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPasswordChange:
    """Test password change flow"""

    def test_change_password_success(self, test_client, auth_headers, test_password):
        """Test successful password change"""
        response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": test_password,
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert "success" in response.json()["message"].lower()

        # Verify can login with new password
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "NewPassword456!"},
        )
        assert login_response.status_code == status.HTTP_200_OK

    def test_change_password_wrong_current(self, test_client, auth_headers):
        """Test password change with incorrect current password"""
        response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "current password" in response.json()["detail"].lower()

    def test_change_password_mismatch(self, test_client, auth_headers, test_password):
        """Test password change with mismatched new passwords"""
        response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": test_password,
                "new_password": "NewPassword456!",
                "confirm_password": "DifferentPassword456!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "do not match" in response.json()["detail"].lower()

    def test_change_password_unauthorized(self, test_client, test_password):
        """Test password change without authentication"""
        response = test_client.post(
            "/api/auth/change-password",
            json={
                "current_password": test_password,
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProtectedEndpoints:
    """Test protected endpoint access"""

    def test_access_profile_authenticated(self, test_client, auth_headers):
        """Test accessing profile with valid token"""
        response = test_client.get("/api/user/profile", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "email" in data
        assert "preferences" in data

    def test_access_profile_unauthenticated(self, test_client):
        """Test accessing profile without token"""
        response = test_client.get("/api/user/profile")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_profile_invalid_token(self, test_client):
        """Test accessing profile with invalid token"""
        response = test_client.get(
            "/api/user/profile", headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuthenticationFlow:
    """Test complete authentication flow"""

    def test_complete_flow(self, test_client, valid_user_data, test_db_session):
        """Test complete user journey: register -> verify email -> login -> access profile -> change password"""
        # 1. Register
        register_response = test_client.post("/api/auth/register", json=valid_user_data)
        assert register_response.status_code == status.HTTP_201_CREATED

        # 2. Verify email (get token from database)
        import asyncio

        from sqlalchemy import select

        from app.models import EmailVerificationToken, User

        async def get_verification_token():
            result = await test_db_session.execute(
                select(EmailVerificationToken)
                .join(User, EmailVerificationToken.user_id == User.id)
                .where(User.email == valid_user_data["email"])
            )
            return result.scalar_one_or_none()

        verification_token = asyncio.run(get_verification_token())
        assert verification_token is not None, "Verification token should be created"

        # Verify the email
        verify_response = test_client.post(
            "/api/auth/verify-email", json={"token": verification_token.token}
        )
        assert verify_response.status_code == status.HTTP_200_OK

        # 3. Login
        login_response = test_client.post(
            "/api/auth/login",
            json={
                "email": valid_user_data["email"],
                "password": valid_user_data["password"],
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.json()
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 4. Access protected endpoint
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert profile_response.status_code == status.HTTP_200_OK

        # 5. Change password
        change_pw_response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": valid_user_data["password"],
                "new_password": "ChangedPass789!",
                "confirm_password": "ChangedPass789!",
            },
        )
        assert change_pw_response.status_code == status.HTTP_200_OK

        # 6. Login with new password
        new_login_response = test_client.post(
            "/api/auth/login",
            json={"email": valid_user_data["email"], "password": "ChangedPass789!"},
        )
        assert new_login_response.status_code == status.HTTP_200_OK


class TestRegistrationLinkFlow:
    """Test registration link (magic link) flow for new users"""

    def test_check_email_new_user(self, test_client):
        """Test checking if email exists - new user"""
        response = test_client.post(
            "/api/auth/check-email", json={"email": "newuser@example.com"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is False
        assert data["requires_password"] is False

    def test_check_email_existing_user(self, test_client, test_user):
        """Test checking if email exists - existing user"""
        response = test_client.post(
            "/api/auth/check-email", json={"email": "test@example.com"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is True
        assert data["requires_password"] is True

    def test_send_registration_link(self, test_client, test_db_session):
        """Test sending registration link to new user"""
        response = test_client.post(
            "/api/auth/send-magic-link", json={"email": "newreg@example.com"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "sent" in data["message"].lower()

    def test_send_registration_link_existing_email(self, test_client, test_user):
        """Test sending registration link to existing email"""
        response = test_client.post(
            "/api/auth/send-magic-link", json={"email": "test@example.com"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"].lower()

    def test_complete_registration_valid_token(self, test_client, test_db_session):
        """Test completing registration with valid token"""
        # First send registration link
        send_response = test_client.post(
            "/api/auth/send-magic-link", json={"email": "complete@example.com"}
        )
        assert send_response.status_code == status.HTTP_200_OK

        # Get the token from database
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(
                    MagicLinkToken.email == "complete@example.com"
                )
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())
        assert magic_token is not None

        # Complete registration
        complete_response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": "NewUserPass123!",
                "confirm_password": "NewUserPass123!",
            },
        )

        assert complete_response.status_code == status.HTTP_201_CREATED
        data = complete_response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "complete@example.com"
        assert data["user"]["email_verified"] is True

    def test_complete_registration_invalid_token(self, test_client):
        """Test completing registration with invalid token"""
        response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": "invalid_token_12345",
                "temp_password": "whatever",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid" in response.json()["detail"].lower()

    def test_complete_registration_wrong_temp_password(
        self, test_client, test_db_session
    ):
        """Test completing registration with wrong temporary password"""
        # Send registration link
        test_client.post(
            "/api/auth/send-magic-link", json={"email": "wrongtemp@example.com"}
        )

        # Get token
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(
                    MagicLinkToken.email == "wrongtemp@example.com"
                )
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())

        # Try to complete with wrong temp password
        response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": "wrong_password",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "temporary password" in response.json()["detail"].lower()

    def test_complete_registration_password_mismatch(
        self, test_client, test_db_session
    ):
        """Test completing registration with mismatched passwords"""
        # Send registration link
        test_client.post(
            "/api/auth/send-magic-link", json={"email": "mismatch@example.com"}
        )

        # Get token
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(
                    MagicLinkToken.email == "mismatch@example.com"
                )
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())

        # Try to complete with mismatched passwords
        response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": "NewPass123!",
                "confirm_password": "DifferentPass123!",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "do not match" in response.json()["detail"].lower()

    def test_complete_registration_weak_password(self, test_client, test_db_session):
        """Test completing registration with weak password"""
        # Send registration link
        test_client.post(
            "/api/auth/send-magic-link", json={"email": "weakpw@example.com"}
        )

        # Get token
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(
                    MagicLinkToken.email == "weakpw@example.com"
                )
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())

        # Try to complete with weak password
        response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": "weak",
                "confirm_password": "weak",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.json()["detail"].lower()

    def test_complete_registration_link_flow(self, test_client, test_db_session):
        """Test complete registration link flow from email check to login"""
        email = "flowtest@example.com"

        # 1. Check email - should not exist
        check_response = test_client.post(
            "/api/auth/check-email", json={"email": email}
        )
        assert check_response.status_code == status.HTTP_200_OK
        assert check_response.json()["exists"] is False

        # 2. Send registration link
        send_response = test_client.post(
            "/api/auth/send-magic-link", json={"email": email}
        )
        assert send_response.status_code == status.HTTP_200_OK

        # 3. Get token from database (simulating user clicking email link)
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(MagicLinkToken.email == email)
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())
        assert magic_token is not None

        # 4. Complete registration
        new_password = "CompleteFlow123!"
        complete_response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )
        assert complete_response.status_code == status.HTTP_201_CREATED
        tokens = complete_response.json()
        assert "access_token" in tokens

        # 5. Verify auto-login works
        profile_response = test_client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert profile_response.status_code == status.HTTP_200_OK
        assert profile_response.json()["email"] == email

        # 6. Verify can login with new password
        login_response = test_client.post(
            "/api/auth/login", json={"email": email, "password": new_password}
        )
        assert login_response.status_code == status.HTTP_200_OK

        # 7. Verify email is already registered now
        check_again_response = test_client.post(
            "/api/auth/check-email", json={"email": email}
        )
        assert check_again_response.json()["exists"] is True

    def test_registration_link_token_reuse_prevention(
        self, test_client, test_db_session
    ):
        """Test that registration link tokens cannot be reused"""
        email = "reuse@example.com"

        # Send registration link
        test_client.post("/api/auth/send-magic-link", json={"email": email})

        # Get token
        import asyncio

        from sqlalchemy import select

        from app.models import MagicLinkToken

        async def get_token():
            result = await test_db_session.execute(
                select(MagicLinkToken).where(MagicLinkToken.email == email)
            )
            return result.scalar_one_or_none()

        magic_token = asyncio.run(get_token())

        # Complete registration once
        first_response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": "FirstUse123!",
                "confirm_password": "FirstUse123!",
            },
        )
        assert first_response.status_code == status.HTTP_201_CREATED

        # Try to use same token again
        second_response = test_client.post(
            "/api/auth/complete-magic-link-registration",
            json={
                "token": magic_token.token,
                "temp_password": magic_token.temp_password,
                "new_password": "SecondUse123!",
                "confirm_password": "SecondUse123!",
            },
        )
        assert second_response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been used" in second_response.json()["detail"].lower()
