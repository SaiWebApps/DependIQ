"""
Tests for user profile and preferences operations
"""

import pytest
from fastapi import status


class TestUserProfile:
    """Test user profile operations"""

    def test_get_profile(self, test_client, auth_headers, test_user):
        """Test getting user profile"""
        response = test_client.get("/api/user/profile", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user.email
        assert data["email_verified"] == test_user.email_verified
        assert "preferences" in data
        assert "oauth_connections" in data

    def test_update_profile_email(self, test_client, auth_headers):
        """Test updating profile email"""
        response = test_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"email": "newemail@example.com"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert "success" in response.json()["message"].lower()

    def test_update_profile_duplicate_email(
        self, test_client, auth_headers, test_user_unverified
    ):
        """Test updating profile with existing email"""
        response = test_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"email": test_user_unverified.email},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already in use" in response.json()["detail"].lower()


class TestUserPreferences:
    """Test user preferences operations"""

    def test_get_preferences(self, test_client, auth_headers):
        """Test getting user preferences"""
        response = test_client.get("/api/user/preferences", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "theme" in data
        assert "language" in data
        assert "timezone" in data
        assert "notifications_enabled" in data

    def test_update_preferences_theme(self, test_client, auth_headers):
        """Test updating theme preference"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "dark"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["theme"] == "dark"

    def test_update_preferences_language(self, test_client, auth_headers):
        """Test updating language preference"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"language": "es"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["language"] == "es"

    def test_update_preferences_timezone(self, test_client, auth_headers):
        """Test updating timezone preference"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"timezone": "America/New_York"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["timezone"] == "America/New_York"

    def test_update_preferences_notifications(self, test_client, auth_headers):
        """Test updating notifications preference"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"notifications_enabled": False},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["notifications_enabled"] is False

    def test_update_preferences_invalid_theme(self, test_client, auth_headers):
        """Test updating with invalid theme"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "invalid"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_preferences_multiple(self, test_client, auth_headers):
        """Test updating multiple preferences at once"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={
                "theme": "dark",
                "language": "fr",
                "timezone": "Europe/Paris",
                "notifications_enabled": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["theme"] == "dark"
        assert data["language"] == "fr"
        assert data["timezone"] == "Europe/Paris"
        assert data["notifications_enabled"] is True


class TestProjectHistory:
    """Test project history operations"""

    @pytest.mark.asyncio
    async def test_get_empty_project_history(self, test_client, auth_headers):
        """Test getting project history when user has no projects"""
        response = test_client.get("/api/user/projects", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) == 0
        assert "pagination" in data

    @pytest.mark.asyncio
    async def test_get_project_history_pagination(self, test_client, auth_headers):
        """Test project history pagination"""
        response = test_client.get(
            "/api/user/projects?page=1&limit=10", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_project_history_filter_by_status(
        self, test_client, auth_headers
    ):
        """Test filtering project history by status"""
        response = test_client.get(
            "/api/user/projects?status=completed", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # All returned projects should have completed status
        for project in data["projects"]:
            assert project["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_project_history_filter_by_source(
        self, test_client, auth_headers
    ):
        """Test filtering project history by source type"""
        response = test_client.get(
            "/api/user/projects?source_type=zip_upload", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # All returned projects should be zip uploads
        for project in data["projects"]:
            assert project["source_type"] == "zip_upload"


class TestOAuthConnections:
    """Test OAuth connection operations"""

    def test_get_oauth_connections_empty(self, test_client, auth_headers):
        """Test getting OAuth connections when user has none"""
        response = test_client.get("/api/user/oauth-connections", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_unlink_nonexistent_oauth(self, test_client, auth_headers):
        """Test unlinking OAuth connection that doesn't exist"""
        response = test_client.delete(
            "/api/user/oauth-connections/github", headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "connection" in response.json()["detail"].lower()


class TestUserProfileIntegration:
    """Test integrated user profile workflows"""

    def test_profile_preferences_workflow(self, test_client, auth_headers):
        """Test complete profile and preferences workflow"""
        # 1. Get initial profile
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert profile_response.status_code == status.HTTP_200_OK
        initial_theme = profile_response.json()["preferences"]["theme"]

        # 2. Update preferences
        new_theme = "dark" if initial_theme == "light" else "light"
        update_response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": new_theme}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # 3. Verify preferences updated in profile
        verify_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.json()["preferences"]["theme"] == new_theme

    def test_profile_update_workflow(self, test_client, auth_headers):
        """Test profile update workflow"""
        # 1. Get current profile
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert profile_response.status_code == status.HTTP_200_OK
        _original_email = profile_response.json()["email"]

        # 2. Update email
        new_email = "updated@example.com"
        update_response = test_client.put(
            "/api/user/profile", headers=auth_headers, json={"email": new_email}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # 3. Verify email changed
        verify_response = test_client.get("/api/user/profile", headers=auth_headers)
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.json()["email"] == new_email.lower()
        # Email verification should be reset
        assert verify_response.json()["email_verified"] is False


class TestUnauthorizedAccess:
    """Test unauthorized access to profile endpoints"""

    def test_get_profile_unauthorized(self, test_client):
        """Test accessing profile without authentication"""
        response = test_client.get("/api/user/profile")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_profile_unauthorized(self, test_client):
        """Test updating profile without authentication"""
        response = test_client.put(
            "/api/user/profile", json={"email": "test@example.com"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_preferences_unauthorized(self, test_client):
        """Test accessing preferences without authentication"""
        response = test_client.get("/api/user/preferences")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_preferences_unauthorized(self, test_client):
        """Test updating preferences without authentication"""
        response = test_client.put("/api/user/preferences", json={"theme": "dark"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_projects_unauthorized(self, test_client):
        """Test accessing project history without authentication"""
        response = test_client.get("/api/user/projects")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_oauth_connections_unauthorized(self, test_client):
        """Test accessing OAuth connections without authentication"""
        response = test_client.get("/api/user/oauth-connections")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
