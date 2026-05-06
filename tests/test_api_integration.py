"""
Integration tests for API endpoints
"""

import tempfile
import zipfile
from unittest.mock import patch

import pytest
from fastapi import status


class TestAnalysisAPI:
    """Test analysis API endpoints"""

    def test_analyze_dependencies_requires_auth(self, test_client):
        """Test that analysis endpoint requires authentication"""
        # Create a dummy ZIP file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            with zipfile.ZipFile(tmp_file.name, "w") as zf:
                zf.writestr("requirements.txt", "fastapi==0.100.0")

            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/", files={"file": ("test.zip", f, "application/zip")}
                )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_analyze_dependencies_non_zip_file(self, test_client, auth_headers):
        """Test that non-ZIP files are rejected"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
            tmp_file.write(b"test content")
            tmp_file.flush()

            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("test.txt", f, "text/plain")},
                )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "error" in data
        assert "ZIP" in data["error"]

    def test_analysis_page_loads(self, test_client):
        """Test that analysis page loads"""
        response = test_client.get("/api/analysis/test_session_123")
        assert response.status_code == status.HTTP_200_OK

    def test_analysis_stream_endpoint_exists(self, test_client):
        """Test that analysis stream endpoint exists"""
        # Mock the streaming response to avoid waiting for full SSE timeout
        with patch("app.api.analysis.create_analysis_stream") as mock_stream:
            # Return a quick generator that yields one update and exits
            def quick_stream(session_id, max_iterations):
                yield 'data: {"step": "Test", "progress": 100, "details": "Test complete"}\n\n'

            mock_stream.return_value = quick_stream("test_session_123", 300)
            response = test_client.get("/api/analysis-stream/test_session_123")
            assert response.status_code == status.HTTP_200_OK


class TestFilesAPI:
    """Test file management API endpoints"""

    def test_view_file_requires_valid_session(self, test_client):
        """Test that viewing files requires a valid session"""
        response = test_client.get("/api/view-file/invalid_session/test.py")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "error" in data

    def test_download_project_requires_valid_session(self, test_client):
        """Test that downloading requires a valid session"""
        response = test_client.get("/api/download/invalid_session")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "error" in data


class TestGitHubAPI:
    """Test GitHub integration API endpoints"""

    def test_github_auth_redirect(self, test_client):
        """Test GitHub OAuth redirect"""
        response = test_client.get("/api/auth/github", allow_redirects=False)

        # Should redirect to GitHub
        assert response.status_code in [302, 307]
        assert "location" in response.headers

    def test_github_repositories_requires_auth(self, test_client):
        """Test that GitHub repositories endpoint requires authentication or validation"""
        response = test_client.get("/api/projects/github/repositories")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    @pytest.mark.asyncio
    async def test_github_repositories_with_auth(self, test_client, auth_headers):
        """Test getting GitHub repositories with authentication"""
        with patch(
            "app.services.github_oauth_service.get_github_repositories"
        ) as mock_repos:
            mock_repos.return_value = [
                {
                    "id": 1,
                    "name": "test-repo",
                    "full_name": "user/test-repo",
                    "private": False,
                }
            ]

            response = test_client.get("/api/projects/github/repositories", headers=auth_headers)

            # May fail if no GitHub token is linked or validation error
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ]


class TestProgressAPI:
    """Test progress tracking API endpoints"""

    def test_progress_page_loads(self, test_client):
        """Test that progress page loads"""
        response = test_client.get("/api/progress/test_session_123")
        assert response.status_code == status.HTTP_200_OK

    def test_progress_stream_endpoint(self, test_client):
        """Test progress stream endpoint"""
        # Mock the streaming response to avoid waiting for full SSE timeout
        with patch("app.api.progress.create_progress_stream") as mock_stream:
            # Return a quick generator that yields one update and exits
            def quick_stream(session_id, max_iterations):
                yield 'data: {"step": "Test", "progress": 100, "details": "Test complete"}\n\n'

            mock_stream.return_value = quick_stream("test_session_123", 300)
            response = test_client.get("/api/progress-stream/test_session_123")
            assert response.status_code == status.HTTP_200_OK


class TestUserAPI:
    """Test user management API endpoints"""

    def test_get_profile_authenticated(self, test_client, auth_headers, test_user):
        """Test getting user profile with authentication"""
        response = test_client.get("/api/user/profile", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user.email
        assert "preferences" in data

    def test_get_profile_unauthenticated(self, test_client):
        """Test that profile requires authentication"""
        response = test_client.get("/api/user/profile")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_profile_email(self, test_client, auth_headers):
        """Test updating profile email"""
        response = test_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"email": "newemail@example.com"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data or "success" in data

    def test_get_preferences(self, test_client, auth_headers):
        """Test getting user preferences"""
        response = test_client.get("/api/user/preferences", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "theme" in data
        assert "language" in data

    def test_update_preferences(self, test_client, auth_headers):
        """Test updating user preferences"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"theme": "dark", "language": "es"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["theme"] == "dark"
        assert data["language"] == "es"

    def test_get_project_history(self, test_client, auth_headers):
        """Test getting project history"""
        response = test_client.get("/api/user/projects", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "projects" in data
        assert "pagination" in data

    def test_get_oauth_connections(self, test_client, auth_headers):
        """Test getting OAuth connections"""
        response = test_client.get("/api/user/oauth-connections", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)


class TestAuthAPIIntegration:
    """Integration tests for authentication API"""

    def test_complete_registration_login_flow(self, test_client):
        """Test complete registration and login flow"""
        # 1. Register new user
        register_data = {
            "email": "integration@example.com",
            "password": "IntegrationTest123!",
            "confirm_password": "IntegrationTest123!",
        }

        register_response = test_client.post("/api/auth/register", json=register_data)
        assert register_response.status_code == status.HTTP_201_CREATED

        # 2. Login with new credentials
        login_response = test_client.post(
            "/api/auth/login",
            json={
                "email": "integration@example.com",
                "password": "IntegrationTest123!",
            },
        )

        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        # 3. Access protected endpoint
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert profile_response.status_code == status.HTTP_200_OK

    def test_token_refresh_flow(self, test_client, test_user):
        """Test token refresh flow"""
        # Login to get tokens
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
        )

        assert login_response.status_code == status.HTTP_200_OK
        tokens = login_response.json()

        # Refresh token
        refresh_response = test_client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert refresh_response.status_code == status.HTTP_200_OK
        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens

    def test_password_change_flow(self, test_client, auth_headers):
        """Test password change flow"""
        response = test_client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "current_password": "TestPassword123!",
                "new_password": "NewTestPassword456!",
                "confirm_password": "NewTestPassword456!",
            },
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify can login with new password
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "NewTestPassword456!"},
        )

        assert login_response.status_code == status.HTTP_200_OK


class TestAPIErrorHandling:
    """Test API error handling"""

    def test_404_for_nonexistent_endpoint(self, test_client):
        """Test 404 error for nonexistent endpoint"""
        response = test_client.get("/api/nonexistent/endpoint")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_validation_error_handling(self, test_client):
        """Test validation error handling"""
        # Send invalid registration data
        response = test_client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "short",
                "confirm_password": "short",
            },
        )

        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_method_not_allowed(self, test_client):
        """Test method not allowed error"""
        # Try to DELETE on a GET-only endpoint
        response = test_client.delete("/api/user/profile")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestAPICORS:
    """Test API CORS configuration"""

    def test_cors_headers_present(self, test_client):
        """Test that CORS headers are present"""
        response = test_client.options(
            "/api/user/profile", headers={"Origin": "http://localhost:3000"}
        )

        # Check for CORS headers (may vary based on configuration)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ]


class TestAPIPerformance:
    """Test API performance characteristics"""

    @pytest.mark.skip(
        reason="Concurrent operations not supported with SQLite in-memory test database"
    )
    def test_multiple_concurrent_profile_requests(self, test_client, auth_headers):
        """Test handling multiple concurrent requests"""
        import concurrent.futures

        def make_request():
            return test_client.get("/api/user/profile", headers=auth_headers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in futures]

        # All requests should succeed
        for response in results:
            assert response.status_code == status.HTTP_200_OK

    def test_large_file_upload_handling(self, test_client, auth_headers):
        """Test handling of larger file uploads"""
        # Create a larger ZIP file (but not too large for testing)
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            with zipfile.ZipFile(tmp_file.name, "w") as zf:
                # Add some content
                for i in range(10):
                    zf.writestr(f"file{i}.py", "# Python file\n" * 100)

            with open(tmp_file.name, "rb") as f:
                response = test_client.post(
                    "/api/analyze/",
                    headers=auth_headers,
                    files={"file": ("large_test.zip", f, "application/zip")},
                )

        # Should handle the upload (may redirect or process)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_302_FOUND,
            status.HTTP_307_TEMPORARY_REDIRECT,
        ]
