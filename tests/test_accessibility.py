"""
Tests for accessibility features
Tests high contrast, colorblind modes, font size, and reduce motion
"""

import pytest
from fastapi import status

from app.models import UserPreference


class TestAccessibilityFieldsInModel:
    """Test accessibility fields in UserPreference model"""

    @pytest.mark.asyncio
    async def test_default_accessibility_settings(self, test_db_session):
        """New user should have default accessibility settings"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id, theme="light", language="en", timezone="UTC"
        )
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        # Check defaults
        assert pref.high_contrast is False
        assert pref.colorblind_mode is None
        assert pref.font_size == "normal"
        assert pref.reduce_motion is False

    @pytest.mark.asyncio
    async def test_set_high_contrast(self, test_db_session):
        """Should be able to enable high contrast"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id,
            theme="light",
            language="en",
            timezone="UTC",
            high_contrast=True,
        )
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        assert pref.high_contrast is True

    @pytest.mark.asyncio
    async def test_set_colorblind_mode(self, test_db_session):
        """Should be able to set colorblind mode"""
        import uuid

        modes = ["protanopia", "deuteranopia", "tritanopia"]

        for mode in modes:
            user_id = uuid.uuid4()
            pref = UserPreference(
                user_id=user_id,
                theme="light",
                language="en",
                timezone="UTC",
                colorblind_mode=mode,
            )
            test_db_session.add(pref)
            await test_db_session.commit()
            await test_db_session.refresh(pref)

            assert pref.colorblind_mode == mode

    @pytest.mark.asyncio
    async def test_set_font_size(self, test_db_session):
        """Should be able to set font size"""
        import uuid

        sizes = ["normal", "large", "xlarge"]

        for size in sizes:
            user_id = uuid.uuid4()
            pref = UserPreference(
                user_id=user_id,
                theme="light",
                language="en",
                timezone="UTC",
                font_size=size,
            )
            test_db_session.add(pref)
            await test_db_session.commit()
            await test_db_session.refresh(pref)

            assert pref.font_size == size

    @pytest.mark.asyncio
    async def test_set_reduce_motion(self, test_db_session):
        """Should be able to enable reduce motion"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id,
            theme="light",
            language="en",
            timezone="UTC",
            reduce_motion=True,
        )
        test_db_session.add(pref)
        await test_db_session.commit()
        await test_db_session.refresh(pref)

        assert pref.reduce_motion is True

    @pytest.mark.asyncio
    async def test_to_dict_includes_accessibility_fields(self, test_db_session):
        """to_dict should include all accessibility fields"""
        import uuid

        user_id = uuid.uuid4()
        pref = UserPreference(
            user_id=user_id,
            theme="ocean",
            language="en",
            timezone="UTC",
            high_contrast=True,
            colorblind_mode="protanopia",
            font_size="large",
            reduce_motion=True,
        )

        result = pref.to_dict()

        assert "high_contrast" in result
        assert result["high_contrast"] is True
        assert "colorblind_mode" in result
        assert result["colorblind_mode"] == "protanopia"
        assert "font_size" in result
        assert result["font_size"] == "large"
        assert "reduce_motion" in result
        assert result["reduce_motion"] is True


class TestAccessibilityAPI:
    """Test accessibility settings API"""

    def test_get_preferences_includes_accessibility(self, test_client, auth_headers):
        """GET preferences should include accessibility fields"""
        response = test_client.get("/api/user/preferences", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check all accessibility fields present
        assert "high_contrast" in data
        assert "colorblind_mode" in data
        assert "font_size" in data
        assert "reduce_motion" in data

    def test_update_high_contrast(self, test_client, auth_headers):
        """Should be able to update high contrast setting"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"high_contrast": True}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["high_contrast"] is True

    def test_update_colorblind_mode(self, test_client, auth_headers):
        """Should be able to set colorblind mode"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"colorblind_mode": "protanopia"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["colorblind_mode"] == "protanopia"

    def test_invalid_colorblind_mode_rejected(self, test_client, auth_headers):
        """Invalid colorblind mode should be rejected"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"colorblind_mode": "invalid_mode"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_font_size(self, test_client, auth_headers):
        """Should be able to set font size"""
        for size in ["normal", "large", "xlarge"]:
            response = test_client.put(
                "/api/user/preferences", headers=auth_headers, json={"font_size": size}
            )

            assert response.status_code == status.HTTP_200_OK
            assert response.json()["font_size"] == size

    def test_invalid_font_size_rejected(self, test_client, auth_headers):
        """Invalid font size should be rejected"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"font_size": "huge"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_reduce_motion(self, test_client, auth_headers):
        """Should be able to toggle reduce motion"""
        response = test_client.put(
            "/api/user/preferences", headers=auth_headers, json={"reduce_motion": True}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["reduce_motion"] is True

    def test_update_multiple_accessibility_settings(self, test_client, auth_headers):
        """Should update multiple accessibility settings at once"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={
                "high_contrast": True,
                "colorblind_mode": "deuteranopia",
                "font_size": "large",
                "reduce_motion": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["high_contrast"] is True
        assert data["colorblind_mode"] == "deuteranopia"
        assert data["font_size"] == "large"
        assert data["reduce_motion"] is True

    def test_clear_colorblind_mode(self, test_client, auth_headers):
        """Should be able to clear colorblind mode"""
        # Set mode first
        test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"colorblind_mode": "protanopia"},
        )

        # Clear it
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"colorblind_mode": None},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["colorblind_mode"] is None


class TestAccessibilityWithThemes:
    """Test accessibility settings work with themes"""

    def test_high_contrast_with_ocean_theme(self, test_client, auth_headers):
        """High contrast should work with ocean theme"""
        response = test_client.put(
            "/api/user/preferences",
            headers=auth_headers,
            json={"theme": "ocean", "high_contrast": True},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["theme"] == "ocean"
        assert data["high_contrast"] is True

    def test_colorblind_mode_with_any_theme(self, test_client, auth_headers):
        """Colorblind mode should work with any theme"""
        themes = ["light", "dark", "ocean", "forest", "nord", "dracula"]

        for theme in themes:
            response = test_client.put(
                "/api/user/preferences",
                headers=auth_headers,
                json={"theme": theme, "colorblind_mode": "protanopia"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["theme"] == theme
            assert data["colorblind_mode"] == "protanopia"
