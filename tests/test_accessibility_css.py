"""
Tests for accessibility CSS features
Tests high contrast, colorblind modes, font sizes, and reduce motion
"""

import re


class TestHighContrastCSS:
    """Test high contrast mode CSS"""

    def test_high_contrast_attribute_defined(self):
        """High contrast CSS should use data-high-contrast attribute"""
        with open("static/css/main.css") as f:
            css = f.read()

        assert 'body[data-high-contrast="true"]' in css

    def test_high_contrast_increases_borders(self):
        """High contrast should increase border thickness"""
        with open("static/css/main.css") as f:
            css = f.read()

        # Check for border-width increase
        high_contrast_block = re.search(
            r'body\[data-high-contrast="true"\][^{]*\{([^}]+)\}', css
        )
        assert high_contrast_block
        assert "--border-width" in high_contrast_block.group(
            1
        ) or "border-width" in high_contrast_block.group(1)

    def test_high_contrast_has_focus_indicators(self):
        """High contrast should have enhanced focus indicators"""
        with open("static/css/main.css") as f:
            css = f.read()

        assert 'data-high-contrast="true"] *:focus' in css
        assert "outline" in css


class TestColorblindCSS:
    """Test colorblind mode CSS"""

    def test_all_colorblind_modes_defined(self):
        """All 3 colorblind modes should have CSS"""
        with open("static/css/main.css") as f:
            css = f.read()

        modes = ["protanopia", "deuteranopia", "tritanopia"]
        for mode in modes:
            assert f'body[data-colorblind="{mode}"]' in css, (
                f"Colorblind mode '{mode}' not found in CSS"
            )

    def test_colorblind_overrides_status_colors(self):
        """Colorblind modes should override status colors"""
        with open("static/css/main.css") as f:
            css = f.read()

        required_overrides = [
            "--color-success",
            "--color-error",
            "--color-warning",
            "--color-info",
        ]

        modes = ["protanopia", "deuteranopia", "tritanopia"]
        for mode in modes:
            # Find colorblind mode block
            pattern = rf'body\[data-colorblind="{mode}"\]\s*\{{([^}}]+)\}}'
            match = re.search(pattern, css)

            assert match, f"Colorblind mode '{mode}' block not found"

            mode_css = match.group(1)
            for color in required_overrides:
                assert color in mode_css, (
                    f"Color '{color}' not overridden in {mode} mode"
                )

    def test_colorblind_colors_avoid_problematic_combinations(self):
        """Colorblind modes should not use red-green combinations"""
        with open("static/css/main.css") as f:
            css = f.read()

        # Protanopia mode should use blue/orange, not red/green
        protanopia_block = re.search(
            r'body\[data-colorblind="protanopia"\]\s*\{([^}]+)\}', css
        )

        if protanopia_block:
            # Should not have pure green (#00FF00) for success in protanopia
            assert "#00FF00" not in protanopia_block.group(1)


class TestFontSizeCSS:
    """Test font size CSS"""

    def test_font_size_options_defined(self):
        """All font size options should have CSS"""
        with open("static/css/main.css") as f:
            css = f.read()

        sizes = ["large", "xlarge"]
        for size in sizes:
            assert f'body[data-font-size="{size}"]' in css, (
                f"Font size '{size}' not found in CSS"
            )

    def test_font_size_increases_base_size(self):
        """Font size modes should increase base font size"""
        with open("static/css/main.css") as f:
            css = f.read()

        # Check large size
        large_block = re.search(r'body\[data-font-size="large"\]\s*\{([^}]+)\}', css)
        assert large_block
        assert "font-size:" in large_block.group(1)

        # Extract font size value
        font_size_match = re.search(r"font-size:\s*(\d+)px", large_block.group(1))
        assert font_size_match
        font_size = int(font_size_match.group(1))
        assert font_size > 15, "Large font should be bigger than default 15px"

    def test_xlarge_bigger_than_large(self):
        """XLarge should be bigger than large"""
        with open("static/css/main.css") as f:
            css = f.read()

        large_match = re.search(
            r'body\[data-font-size="large"\]\s*\{[^}]*font-size:\s*(\d+)px', css
        )
        xlarge_match = re.search(
            r'body\[data-font-size="xlarge"\]\s*\{[^}]*font-size:\s*(\d+)px', css
        )

        if large_match and xlarge_match:
            large_size = int(large_match.group(1))
            xlarge_size = int(xlarge_match.group(1))
            assert xlarge_size > large_size, "XLarge should be bigger than large"


class TestReduceMotionCSS:
    """Test reduce motion CSS"""

    def test_reduce_motion_defined(self):
        """Reduce motion CSS should exist"""
        with open("static/css/main.css") as f:
            css = f.read()

        assert 'body[data-reduce-motion="true"]' in css

    def test_reduce_motion_affects_animations(self):
        """Reduce motion should disable animations"""
        with open("static/css/main.css") as f:
            css = f.read()

        reduce_motion_block = re.search(
            r'body\[data-reduce-motion="true"\][^{]*\{([^}]+)\}', css, re.DOTALL
        )

        assert reduce_motion_block
        block_content = reduce_motion_block.group(1)

        # Should affect animation or transition duration
        assert (
            "animation-duration" in block_content
            or "transition-duration" in block_content
        )

    def test_reduce_motion_affects_transitions(self):
        """Reduce motion should minimize transition durations"""
        with open("static/css/main.css") as f:
            css = f.read()

        # Should set very short durations
        assert (
            "transition-duration: 0.01ms" in css or "animation-duration: 0.01ms" in css
        )


class TestAccessibilityCSSStructure:
    """Test accessibility CSS organization"""

    def test_accessibility_section_commented(self):
        """Accessibility CSS should have descriptive header"""
        with open("static/css/main.css") as f:
            css = f.read()

        assert "ACCESSIBILITY" in css.upper() or "accessibility" in css.lower()

    def test_accessibility_css_after_themes(self):
        """Accessibility CSS should come after theme definitions"""
        with open("static/css/main.css") as f:
            css = f.read()

        # Find positions
        dracula_pos = css.find('body[data-theme="dracula"]')
        accessibility_pos = css.find("data-high-contrast")

        if dracula_pos >= 0 and accessibility_pos >= 0:
            assert accessibility_pos > dracula_pos, (
                "Accessibility CSS should come after theme definitions"
            )
