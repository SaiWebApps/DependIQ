"""
Comprehensive tests for theme system
Tests theme validation, persistence, and switching
"""

import pytest
from fastapi import status

from app.models import UserPreference


class TestThemeValidation:
    """Test theme validation logic"""

    def test_all_valid_themes_accepted(self, test_client, auth_headers):
        """All 7 valid themes should be accepted"""
        valid_themes = ["light", "dark", "ocean", "forest", "nord", "dracula", "system"]

        for theme in valid_themes:
            response = test_client.put(
                "/api/user/preferences", headers=auth_headers, json={"theme": theme}
            )

            assert response.status_code == status.HTTP_200_OK, (
                f"Theme '{theme}' should be valid but got {response.status_code}"
            )
            data = response.json()
            assert data["theme"] == theme

    def test_invalid_theme_rejected(self, test_client, auth_headers):
        """Invalid themes should be rejected with 400"""
        invalid_themes = ["rainbow", "cosmic", "invalid", ""]

        for theme in invalid_themes:
            response = test_client.put(
                "/api/user/preferences", headers=auth_headers, json={"theme": theme}
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST, (
                f"Theme '{theme}' should be rejected"
            )
            assert "must be one of" in response.json()["detail"].lower()

    def test_theme_case_sensitive(self, test_client, auth_headers):
        """Theme names should be case-sensitive"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "DARK"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestThemeModel:
    """Test UserPreference model theme functionality"""

    @pytest.mark.asyncio
    async def test_theme_field_length(self, test_db_session):
        """Theme field should accommodate all theme names"""
        import uuid

        # Test longest theme name
        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id,
            theme="dracula",  # 8 characters
            language="en",
            timezone="UTC",
        )
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        assert pref.theme == "dracula"

    @pytest.mark.asyncio
    async def test_default_theme_is_light(self, test_db_session):
        """Default theme should be 'light'"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(user_id=user_id, language="en", timezone="UTC")
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        assert pref.theme == "light"

    @pytest.mark.asyncio
    async def test_theme_auto_mode_nullable(self, test_db_session):
        """theme_auto_mode should be nullable"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id, theme="system", language="en", timezone="UTC"
        )
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        assert pref.theme_auto_mode is None  # Should allow None

    @pytest.mark.asyncio
    async def test_to_dict_includes_theme(self, test_db_session):
        """to_dict should include theme"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id, theme="ocean", language="en", timezone="UTC"
        )

        result = pref.to_dict()
        assert "theme" in result
        assert result["theme"] == "ocean"


class TestThemePersistence:
    """Test theme persistence across sessions"""

    def test_theme_persists_after_update(self, test_client, auth_headers):
        """Theme should persist after update"""
        # Set theme to ocean
        update_response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "ocean"}
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Get preferences again
        get_response = test_client.get("/api/user/preferences", headers=auth_headers)
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["theme"] == "ocean"

    def test_theme_in_profile_response(self, test_client, auth_headers):
        """Theme should be included in profile response"""
        # Update theme
        test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "nord"}
        )

        # Get full profile
        profile_response = test_client.get("/api/user/profile", headers=auth_headers)

        assert profile_response.status_code == status.HTTP_200_OK
        data = profile_response.json()
        assert data["preferences"]["theme"] == "nord"

    def test_multiple_theme_updates(self, test_client, auth_headers):
        """Should handle multiple rapid theme updates"""
        themes_sequence = ["ocean", "forest", "nord", "dracula", "dark", "light"]

        for theme in themes_sequence:
            response = test_client.put(
                "/api/user/preferences", headers=auth_headers, json={"theme": theme}
            )
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["theme"] == theme


class TestThemeWithOtherPreferences:
    """Test theme updates alongside other preferences"""

    def test_update_theme_preserves_other_prefs(self, test_client, auth_headers):
        """Updating theme should not affect other preferences"""
        # Set initial preferences
        test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={
                "theme": "light",
                "language": "es",
                "timezone": "Europe/Madrid",
                "notifications_enabled": False,
            },
        )

        # Update only theme
        test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "ocean"}
        )

        # Verify other preferences unchanged
        response = test_client.get("/api/user/preferences", headers=auth_headers)
        data = response.json()

        assert data["theme"] == "ocean"
        assert data["language"] == "es"
        assert data["timezone"] == "Europe/Madrid"
        assert data["notifications_enabled"] is False

    def test_update_all_preferences_including_theme(self, test_client, auth_headers):
        """Should update all preferences including theme"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={
                "theme": "dracula",
                "language": "fr",
                "timezone": "Europe/Paris",
                "notifications_enabled": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["theme"] == "dracula"
        assert data["language"] == "fr"
        assert data["timezone"] == "Europe/Paris"
        assert data["notifications_enabled"] is True


class TestNewThemes:
    """Test Phase 1 new themes specifically"""

    def test_ocean_theme(self, test_client, auth_headers):
        """Ocean theme should work"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "ocean"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["theme"] == "ocean"

    def test_forest_theme(self, test_client, auth_headers):
        """Forest theme should work"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "forest"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["theme"] == "forest"

    def test_nord_theme(self, test_client, auth_headers):
        """Nord theme should work"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "nord"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["theme"] == "nord"

    def test_dracula_theme(self, test_client, auth_headers):
        """Dracula theme should work"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "dracula"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["theme"] == "dracula"

    def test_system_theme(self, test_client, auth_headers):
        """System auto-detection theme should work"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"theme": "system"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["theme"] == "system"
