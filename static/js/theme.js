// DependIQ Theme Manager
// Applies theme and accessibility settings immediately on page load
(function () {
    'use strict';

    /**
     * Detect the system's color scheme preference
     */
    function detectSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }

    /**
     * Apply theme to the page
     */
    function applyTheme(theme) {
        document.body.removeAttribute('data-theme');
        document.body.classList.remove('dark-mode');

        const darkThemes = ['dark', 'ocean', 'forest', 'nord', 'dracula'];
        if (darkThemes.includes(theme)) {
            document.body.classList.add('dark-mode');
        }

        if (theme !== 'light' && theme !== 'dark') {
            document.body.setAttribute('data-theme', theme);
        }
    }

    /**
     * Setup listener for system theme changes
     */
    function setupSystemThemeListener() {
        if (window.matchMedia) {
            const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');

            if (darkModeQuery.addEventListener) {
                darkModeQuery.addEventListener('change', function (e) {
                    if (localStorage.getItem('theme') === 'system') {
                        const newTheme = e.matches ? 'dark' : 'light';
                        applyTheme(newTheme);
                        localStorage.setItem('effective-theme', newTheme);
                    }
                });
            }
        }
    }

    /**
     * Apply accessibility settings to the page
     */
    function applyAccessibilitySettings(settings) {
        if (!document.body) {
            return false;
        }

        // High contrast
        if (settings.high_contrast) {
            document.body.setAttribute('data-high-contrast', 'true');
        } else {
            document.body.removeAttribute('data-high-contrast');
        }

        // Colorblind mode
        if (settings.colorblind_mode) {
            document.body.setAttribute('data-colorblind', settings.colorblind_mode);
        } else {
            document.body.removeAttribute('data-colorblind');
        }

        // Font size
        if (settings.font_size && settings.font_size !== 'normal') {
            document.body.setAttribute('data-font-size', settings.font_size);
        } else {
            document.body.removeAttribute('data-font-size');
        }

        // Reduce motion
        if (settings.reduce_motion) {
            document.body.setAttribute('data-reduce-motion', 'true');
        } else {
            document.body.removeAttribute('data-reduce-motion');
        }

        localStorage.setItem('accessibility_settings', JSON.stringify(settings));
        return true;
    }

    /**
     * Initialize theme and accessibility on page load
     */
    function initialize() {
        // Apply theme
        const storedTheme = localStorage.getItem('theme') || 'light';

        if (storedTheme === 'system') {
            const systemTheme = detectSystemTheme();
            applyTheme(systemTheme);
            localStorage.setItem('effective-theme', systemTheme);
            setupSystemThemeListener();
        } else {
            applyTheme(storedTheme);
        }

        // Apply accessibility
        const storedSettings = localStorage.getItem('accessibility_settings');
        if (storedSettings) {
            try {
                const settings = JSON.parse(storedSettings);
                applyAccessibilitySettings(settings);
            } catch (e) {
                console.error('Failed to parse accessibility settings:', e);
            }
        }
    }

    // Expose functions globally BEFORE initialization
    window.DependIQTheme = {
        detectSystemTheme: detectSystemTheme,
        applyTheme: applyTheme,
        setupSystemThemeListener: setupSystemThemeListener,
        applyAccessibilitySettings: applyAccessibilitySettings
    };

    // Initialize when DOM is ready
    if (document.body) {
        initialize();
    } else {
        document.addEventListener('DOMContentLoaded', initialize);
    }

})();
