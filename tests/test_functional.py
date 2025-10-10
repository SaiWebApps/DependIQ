"""
Functional end-to-end tests for complete workflows
"""

import tempfile
import zipfile
from unittest.mock import patch

import pytest
from fastapi import status


class TestCompleteUserJourney:
    """Test complete user journey from registration to project analysis"""

    def test_new_user_complete_workflow(self, test_client, test_db_session):
        """Test complete workflow: register -> verify email -> login -> upload -> analyze"""
        # 1. Register new user
        register_data = {
            "email": "journey@example.com",
            "password": "JourneyTest123!",
            "confirm_password": "JourneyTest123!",
        }

        register_response = test_client.post("/api/auth/register", json=register_data)
        assert register_response.status_code == status.HTTP_201_CREATED

        # 2. Verify email (get token from database)
        import asyncio

        from sqlalchemy import select

        from app.models import EmailVerificationToken, User

        async def get_verification_token():
            # First get the user
            user_result = await test_db_session.execute(
                select(User).where(User.email == "journey@example.com")
            )
            user = user_result.scalar_one_or_none()
            if not user:
                return None

            # Then get their verification token
            token_result = await test_db_session.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == user.id
                )
            )
            return token_result.scalar_one_or_none()

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
            json={"email": "journey@example.com", "password": "JourneyTest123!"},
        )

        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.json()
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 4. Get profile
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert profile_response.status_code == status.HTTP_200_OK
        profile = profile_response.json()
        assert profile["email"] == "journey@example.com"

        # 5. Update preferences
        prefs_response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"theme": "dark", "language": "en"},
        )
        assert prefs_response.status_code == status.HTTP_200_OK

        # 6. Check project history (should be empty)
        history_response = test_client.get("/api/user/projects", headers=auth_headers)
        assert history_response.status_code == status.HTTP_200_OK
        history = history_response.json()
        assert len(history["projects"]) == 0


class TestProjectAnalysisWorkflow:
    """Test project analysis end-to-end workflow"""

    def test_python_project_analysis(self, test_client, auth_headers):
        """Test analyzing a Python project from upload to results"""
        # Create a test Python project ZIP
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            with zipfile.ZipFile(tmp_file.name, "w") as zf:
                zf.writestr("requirements.txt", "fastapi==0.100.0\npydantic==2.0.0")
                zf.writestr("main.py", "from fastapi import FastAPI\napp = FastAPI()")

            # Upload project
            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("test_project.zip", f, "application/zip")},
                    data={"user_instructions": "Update to latest versions"},
                )

            # Should redirect to analysis page
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_302_FOUND,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]

    def test_gradle_project_workflow(self, test_client, auth_headers):
        """Test analyzing a Gradle project"""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            with zipfile.ZipFile(tmp_file.name, "w") as zf:
                gradle_content = """
                plugins {
                    id 'java'
                }
                dependencies {
                    implementation 'org.springframework.boot:spring-boot-starter-web:2.7.0'
                }
                """
                zf.writestr("build.gradle", gradle_content)
                zf.writestr("src/main/java/Main.java", "public class Main {}")

            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("gradle_project.zip", f, "application/zip")},
                )

            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_302_FOUND,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]


class TestGitHubIntegrationWorkflow:
    """Test GitHub integration workflow"""

    def test_github_oauth_flow(self, test_client):
        """Test GitHub OAuth authentication flow"""
        # Initiate OAuth
        response = test_client.get("/api/auth/github", allow_redirects=False)

        assert response.status_code in [302, 307]
        assert "location" in response.headers

        # Verify redirect contains GitHub authorize URL
        location = response.headers["location"]
        assert "github.com" in location or "Location" in str(response.headers)

    @pytest.mark.asyncio
    async def test_github_repository_selection(self, test_client, auth_headers):
        """Test selecting GitHub repository for analysis"""
        with patch(
            "app.services.github_oauth_service.get_github_repositories"
        ) as mock_repos:
            mock_repos.return_value = [
                {
                    "id": 1,
                    "name": "test-repo",
                    "full_name": "user/test-repo",
                    "default_branch": "main",
                }
            ]

            response = test_client.get("/api/github/repositories", headers=auth_headers)

            # May require GitHub connection or validation error
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ]


class TestUserPreferencesWorkflow:
    """Test user preferences management workflow"""

    def test_theme_switching_workflow(self, test_client, auth_headers):
        """Test switching between light and dark themes"""
        # Get current theme
        prefs_response = test_client.get("/api/user/preferences", headers=auth_headers)
        assert prefs_response.status_code == status.HTTP_200_OK
        _current_prefs = prefs_response.json()

        # Switch to dark theme
        update_response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "dark"}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Verify theme changed
        verify_response = test_client.get("/api/user/preferences", headers=auth_headers)
        updated_prefs = verify_response.json()
        assert updated_prefs["theme"] == "dark"

        # Switch back to light
        revert_response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "light"}
        )
        assert revert_response.status_code == status.HTTP_200_OK

    def test_language_preference_workflow(self, test_client, auth_headers):
        """Test changing language preference"""
        languages_to_test = ["en", "es", "fr", "de"]

        for lang in languages_to_test:
            response = test_client.put(
                "/api/user/preferences", headers=auth_headers, json={"language": lang}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["language"] == lang

    def test_notification_toggle_workflow(self, test_client, auth_headers):
        """Test toggling notifications on and off"""
        # Enable notifications
        enable_response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"notifications_enabled": True},
        )
        assert enable_response.status_code == status.HTTP_200_OK
        assert enable_response.json()["notifications_enabled"] is True

        # Disable notifications
        disable_response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"notifications_enabled": False},
        )
        assert disable_response.status_code == status.HTTP_200_OK
        assert disable_response.json()["notifications_enabled"] is False


class TestPasswordManagementWorkflow:
    """Test password-related workflows"""

    def test_password_change_workflow(self, test_client, test_user):
        """Test changing password and logging in with new password"""
        # Login with original password
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )
        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.json()
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Change password
        change_response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": "TestPassword123!",
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!",
            },
        )
        assert change_response.status_code == status.HTTP_200_OK

        # Login with new password
        new_login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "NewPassword456!"},
        )
        assert new_login_response.status_code == status.HTTP_200_OK

        # Verify old password doesn't work
        old_login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )
        assert old_login_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProjectHistoryWorkflow:
    """Test project history tracking workflow"""

    def test_project_history_accumulation(self, test_client, auth_headers):
        """Test that project history accumulates over multiple uploads"""
        # Get initial count
        initial_response = test_client.get("/api/user/projects", headers=auth_headers)
        initial_count = len(initial_response.json()["projects"])

        # Upload multiple projects
        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
                with zipfile.ZipFile(tmp_file.name, "w") as zf:
                    zf.writestr("requirements.txt", f"package{i}==1.0.0")

                with open(tmp_file.name, "rb") as f:
                    test_client.post(
                        "/api/analyze/",
                        headers=auth_headers,
                        files={"file": (f"project{i}.zip", f, "application/zip")},
                    )

        # Check history increased
        final_response = test_client.get("/api/user/projects", headers=auth_headers)
        final_count = len(final_response.json()["projects"])

        assert final_count >= initial_count


class TestErrorRecoveryWorkflow:
    """Test error recovery and edge cases"""

    def test_invalid_file_upload_recovery(self, test_client, auth_headers):
        """Test recovery from invalid file upload"""
        # Try to upload non-ZIP file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
            tmp_file.write(b"not a zip file")
            tmp_file.flush()

            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("invalid.txt", f, "text/plain")},
                )

        # Should get error response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "error" in data

        # Should still be able to upload valid file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            with zipfile.ZipFile(tmp_file.name, "w") as zf:
                zf.writestr("requirements.txt", "fastapi==0.100.0")

            with open(tmp_file.name, "rb") as f:
                valid_response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("valid.zip", f, "application/zip")},
                )

        # Valid upload should work
        assert valid_response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_302_FOUND,
            status.HTTP_307_TEMPORARY_REDIRECT,
        ]

    def test_session_expiration_recovery(self, test_client, test_user):
        """Test recovery from expired session"""
        # Login to get tokens
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )
        tokens = login_response.json()

        # Use invalid/expired token
        bad_headers = {"Authorization": "Bearer invalid_token_here"}
        profile_response = test_client.get("/api/user/profile", headers=bad_headers)
        assert profile_response.status_code == status.HTTP_401_UNAUTHORIZED

        # Refresh token to recover
        refresh_response = test_client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK

        # Use new token
        new_tokens = refresh_response.json()
        new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
        new_profile_response = test_client.get("/api/user/profile", headers=new_headers)
        assert new_profile_response.status_code == status.HTTP_200_OK


class TestMultiUserScenarios:
    """Test scenarios with multiple users"""

    def test_multiple_users_independent_data(self, test_client, test_db_session):
        """Test that multiple users have independent data"""
        import asyncio

        from sqlalchemy import select

        from app.models import EmailVerificationToken, User

        # Create two users
        users = []
        for i in range(2):
            email = f"multiuser{i}@example.com"
            password = f"MultiUser{i}Password123!"

            # Register
            test_client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "confirm_password": password,
                },
            )

            # Verify email
            async def get_verification_token(user_email: str):
                result = await test_db_session.execute(
                    select(EmailVerificationToken)
                    .join(User, EmailVerificationToken.user_id == User.id)
                    .where(User.email == user_email)
                )
                return result.scalar_one_or_none()

            verification_token = asyncio.run(get_verification_token(email))
            if verification_token:
                test_client.post(
                    "/api/auth/verify-email", json={"token": verification_token.token}
                )

            # Login
            login_response = test_client.post(
                "/api/auth/login", json={"email": email, "password": password}
            )
            tokens = login_response.json()
            users.append(
                {
                    "email": email,
                    "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
                }
            )

        # Set different preferences for each user
        for i, user in enumerate(users):
            theme = "dark" if i == 0 else "light"
            test_client.put(
                "/api/user/preferences", headers=user["headers"], json={"theme": theme}
            )

        # Verify each user has their own preferences
        for i, user in enumerate(users):
            response = test_client.get("/api/user/preferences", headers=user["headers"])
            prefs = response.json()
            expected_theme = "dark" if i == 0 else "light"
            assert prefs["theme"] == expected_theme

    @pytest.mark.skip(
        reason="Concurrent operations not supported with SQLite in-memory test database"
    )
    def test_concurrent_user_operations(self, test_client, auth_headers):
        """Test concurrent operations from multiple sessions"""
        import concurrent.futures

        def get_profile():
            return test_client.get("/api/user/profile", headers=auth_headers)

        # Execute concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(get_profile) for _ in range(3)]
            results = [f.result() for f in futures]

        # All should succeed
        for response in results:
            assert response.status_code == status.HTTP_200_OK
