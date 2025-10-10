"""
Tests for theme CSS definitions
Validates that all themes have proper CSS and required variables
"""

import re


class TestThemeCSSDefinitions:
    """Test that all themes have CSS definitions"""

    def test_all_themes_have_css_definitions(self):
        """Each theme should have CSS definition in main.css"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        themes = ["ocean", "forest", "nord", "dracula"]

        for theme in themes:
            # Check for theme definition
            pattern = rf'body\[data-theme="{theme}"\]\s*\{{'
            assert re.search(
                pattern, css_content
            ), f"Theme '{theme}' not defined in main.css"

    def test_dark_mode_css_exists(self):
        """Dark mode CSS should exist"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        assert "body.dark-mode" in css_content, "Dark mode CSS not found"

    def test_theme_has_required_css_variables(self):
        """Each theme should define all required CSS variables"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        required_variables = [
            "--color-background",
            "--color-surface",
            "--color-primary",
            "--color-secondary",
            "--color-tertiary",
            "--color-border",
            "--color-hover",
            "--color-accent",
        ]

        themes = ["ocean", "forest", "nord", "dracula"]

        for theme in themes:
            # Extract theme CSS block
            pattern = rf'body\[data-theme="{theme}"\]\s*\{{([^}}]+)\}}'
            match = re.search(pattern, css_content)

            assert match, f"Theme '{theme}' CSS block not found"

            theme_css = match.group(1)

            for var in required_variables:
                assert (
                    var in theme_css
                ), f"Variable '{var}' not defined for theme '{theme}'"

    def test_root_variables_defined(self):
        """Root CSS variables should be defined"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        # Find :root block
        root_match = re.search(r":root\s*\{([^}]+)\}", css_content)
        assert root_match, ":root block not found in CSS"

        root_css = root_match.group(1)

        required_root_vars = [
            "--color-background",
            "--color-surface",
            "--color-primary",
            "--spacing-xs",
            "--spacing-sm",
            "--font-family",
        ]

        for var in required_root_vars:
            assert var in root_css, f"Root variable '{var}' not defined"


class TestThemeCSSStructure:
    """Test CSS structure and organization"""

    def test_dark_themes_have_dark_mode_styles(self):
        """Dark-based themes should have supporting styles"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        dark_themes = ["ocean", "forest", "nord", "dracula"]

        for theme in dark_themes:
            # Check for sidebar styles
            pattern = rf'body\[data-theme="{theme}"\]\s+\.sidebar'
            assert re.search(
                pattern, css_content
            ), f"Theme '{theme}' missing sidebar styles"

            # Check for stat-card styles
            pattern = rf'body\[data-theme="{theme}"\]\s+\.stat-card'
            assert re.search(
                pattern, css_content
            ), f"Theme '{theme}' missing stat-card styles"

    def test_css_file_size_reasonable(self):
        """CSS file should not be excessively large"""
        import os

        file_size = os.path.getsize("static/css/main.css")

        # Should be less than 200KB
        assert file_size < 200 * 1024, f"CSS file too large: {file_size} bytes"


class TestCSSColorValues:
    """Test that colors are valid hex codes"""

    def test_color_values_are_valid_hex(self):
        """All color values should be valid hex codes"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        # Find all CSS variable definitions
        color_pattern = r"--color-\w+:\s*(#[0-9a-fA-F]{3,8})"
        matches = re.findall(color_pattern, css_content)

        assert len(matches) > 0, "No color variables found"

        hex_pattern = r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"

        for color_value in matches:
            assert re.match(
                hex_pattern, color_value
            ), f"Invalid hex color: {color_value}"

    def test_accent_colors_defined(self):
        """Each theme should have status colors"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        status_colors = [
            "--color-success",
            "--color-error",
            "--color-warning",
            "--color-info",
        ]

        # Check in root
        for color in status_colors:
            assert color in css_content, f"Status color '{color}' not defined"


class TestCSSComments:
    """Test CSS documentation and comments"""

    def test_themes_have_descriptive_comments(self):
        """Each theme section should have descriptive comments"""
        with open("static/css/main.css") as f:
            css_content = f.read()

        themes = ["Ocean", "Forest", "Nord", "Dracula"]

        for theme in themes:
            assert (
                f"/* {theme}" in css_content
            ), f"Theme '{theme}' missing descriptive comment"
