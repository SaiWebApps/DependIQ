"""
Functional end-to-end tests for complete workflows.

With WorkOS AuthKit, authentication is cookie-based. Tests mock the session
verification to simulate authenticated users.
"""

import tempfile
import zipfile
from unittest.mock import patch

import pytest
from fastapi import status

from app.services.workos_auth import SESSION_COOKIE_NAME
from tests.conftest import TEST_SESSION_TOKEN, TEST_WORKOS_USER_ID


@pytest.fixture
def auth_cookies():
    """Session cookie for authenticated requests."""
    return {SESSION_COOKIE_NAME: TEST_SESSION_TOKEN}


@pytest.fixture
def mock_session_verification(test_user):
    """Mock session verification for functional tests that need it."""
    from workos.session import AuthenticateWithSessionCookieSuccessResponse

    with patch("app.services.workos_auth.verify_or_refresh_session") as mock_verify:
        mock_verify.return_value = (AuthenticateWithSessionCookieSuccessResponse(
            authenticated=True,
            session_id="sess_func_test",
            user={"id": TEST_WORKOS_USER_ID, "email": "test@example.com"},
        ), None)
        yield mock_verify


class TestProjectAnalysisWorkflow:
    """Test project analysis end-to-end workflow"""

    def test_python_project_analysis(self, test_client, test_user, auth_cookies, mock_session_verification):
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
                    cookies=auth_cookies,
                    files={"file": ("test_project.zip", f, "application/zip")},
                    data={"user_instructions": "Update to latest versions"},
                )

            # Should redirect to analysis page
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_302_FOUND,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]

    def test_gradle_project_workflow(self, test_client, test_user, auth_cookies, mock_session_verification):
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
                    cookies=auth_cookies,
                    files={"file": ("gradle_project.zip", f, "application/zip")},
                )

            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_302_FOUND,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]


class TestGitHubIntegrationWorkflow:
    """Test GitHub integration workflow"""

    def test_github_login_redirects(self, test_client):
        """Test that /api/auth/login?provider=GitHubOAuth redirects."""
        with patch("app.api.auth.get_authorization_url") as mock_url:
            mock_url.return_value = ("https://authkit.workos.com/authorize", "state_gh")

            response = test_client.get(
                "/api/auth/login?provider=GitHubOAuth",
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert "authkit.workos.com" in response.headers["location"]

    def test_github_repository_selection(
        self, test_client, test_user_with_github, auth_cookies
    ):
        """Test selecting GitHub repository for analysis."""
        # Override the autouse mock to use the github user's workos_id
        from workos.session import AuthenticateWithSessionCookieSuccessResponse

        from tests.conftest import TEST_GITHUB_WORKOS_USER_ID

        with patch("app.services.workos_auth.verify_or_refresh_session") as mock_v:
            mock_v.return_value = (AuthenticateWithSessionCookieSuccessResponse(
                authenticated=True,
                session_id="sess_func_github",
                user={"id": TEST_GITHUB_WORKOS_USER_ID, "email": "github@example.com"},
            ), None)

            with patch(
                "app.api.projects.get_github_repositories"
            ) as mock_repos:
                mock_repos.return_value = [
                    {
                        "id": 1,
                        "name": "test-repo",
                        "full_name": "user/test-repo",
                        "default_branch": "main",
                    }
                ]

                response = test_client.get(
                    "/api/projects/github/repositories",
                    cookies=auth_cookies,
                )

                assert response.status_code == 200
                repos = response.json()
                assert len(repos) == 1
                assert repos[0]["name"] == "test-repo"


class TestUserPreferencesWorkflow:
    """Test user preferences management workflow"""

    def test_theme_switching_workflow(self, test_client, test_user, auth_cookies, mock_session_verification):
        """Test switching between light and dark themes"""
        # Get current theme
        prefs_response = test_client.get(
            "/api/user/preferences", cookies=auth_cookies
        )
        assert prefs_response.status_code == status.HTTP_200_OK

        # Switch to dark theme
        update_response = test_client.put(
            "/api/user/preferences",
            cookies=auth_cookies,
            json={"theme": "dark"},
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Verify theme changed
        verify_response = test_client.get(
            "/api/user/preferences", cookies=auth_cookies
        )
        updated_prefs = verify_response.json()
        assert updated_prefs["theme"] == "dark"

        # Switch back to light
        revert_response = test_client.put(
            "/api/user/preferences",
            cookies=auth_cookies,
            json={"theme": "light"},
        )
        assert revert_response.status_code == status.HTTP_200_OK

    def test_language_preference_workflow(self, test_client, test_user, auth_cookies, mock_session_verification):
        """Test changing language preference"""
        languages_to_test = ["en", "es", "fr", "de"]

        for lang in languages_to_test:
            response = test_client.put(
                "/api/user/preferences",
                cookies=auth_cookies,
                json={"language": lang},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["language"] == lang

    def test_notification_toggle_workflow(self, test_client, test_user, auth_cookies, mock_session_verification):
        """Test toggling notifications on and off"""
        # Enable notifications
        enable_response = test_client.put(
            "/api/user/preferences",
            cookies=auth_cookies,
            json={"notifications_enabled": True},
        )
        assert enable_response.status_code == status.HTTP_200_OK
        assert enable_response.json()["notifications_enabled"] is True

        # Disable notifications
        disable_response = test_client.put(
            "/api/user/preferences",
            cookies=auth_cookies,
            json={"notifications_enabled": False},
        )
        assert disable_response.status_code == status.HTTP_200_OK
        assert disable_response.json()["notifications_enabled"] is False
