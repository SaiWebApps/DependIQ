"""
Artifact exclusion configuration for filtering build artifacts and temporary files
"""

from pathlib import Path
from typing import ClassVar


class ArtifactExclusionConfig:
    """
    High-performance configuration for artifact exclusion patterns and directories.

    Uses optimized data structures and caching for better performance in large projects.
    """

    # Standard directories to exclude across project types (using frozenset for immutability and performance)
    COMMON_EXCLUDED_DIRS: frozenset[str] = frozenset(
        {
            "target",
            "build",
            ".gradle",
            "__pycache__",
            ".git",
            "node_modules",
            ".idea",
            ".vscode",
            ".metals",
            ".bsp",
            ".pytest_cache",
            ".mypy_cache",
            "dist",
            ".tox",
            ".venv",
            "venv",
            "env",
            ".env",
            "coverage",
            ".coverage",
            ".nyc_output",
        }
    )

    # Standard file patterns to exclude (using frozenset for faster lookups)
    COMMON_EXCLUDED_PATTERNS: frozenset[str] = frozenset(
        {
            "*.class",
            "*.jar",
            "*.log",
            "*.tmp",
            "*.cache",
            "*.bak",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            "*.so",
            "*.dll",
            "*.dylib",
            "*.exe",
            "*.war",
            "*.ear",
            "*.zip",
            "*.tar.gz",
            "*.rar",
        }
    )

    # Important build files that should never be excluded (frozenset for performance)
    IMPORTANT_BUILD_FILES: frozenset[str] = frozenset(
        {
            "build.sbt",
            "build.gradle",
            "build.gradle.kts",
            "pom.xml",
            "requirements.txt",
            "package.json",
            "Cargo.toml",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "poetry.lock",
            "yarn.lock",
            "package-lock.json",
            "composer.json",
            "go.mod",
            "Gemfile",
        }
    )

    # Cache for compiled patterns to avoid repeated regex compilation
    _pattern_cache: ClassVar[dict[str, dict[str, list[str] | str]]] = {}

    @classmethod
    def get_fallback_exclusions(
        cls, reason: str = "parsing failure"
    ) -> dict[str, list[str] | str]:
        """
        Get fallback exclusion configuration with consistent structure.

        Performance optimized with cached list creation to avoid repeated conversions.

        Args:
            reason: The reason for using fallback exclusions

        Returns:
            Dictionary with directories, patterns, and reasoning
        """
        # Use tuple conversion for better memory efficiency than list
        cache_key = f"fallback_{reason}"
        if cache_key not in cls._pattern_cache:
            cls._pattern_cache[cache_key] = {
                "directories": list(cls.COMMON_EXCLUDED_DIRS),
                "patterns": list(cls.COMMON_EXCLUDED_PATTERNS),
                "reasoning": f"Fallback exclusions due to {reason}",
            }
        return cls._pattern_cache[cache_key].copy()  # Return copy to prevent mutation

    @classmethod
    def should_exclude_file(
        cls, file_path: str, excluded_dirs: set[str], excluded_patterns: set[str]
    ) -> tuple[bool, str | None]:
        """
        High-performance file exclusion check.

        Args:
            file_path: Path to check for exclusion
            excluded_dirs: Set of directory names to exclude
            excluded_patterns: Set of file patterns to exclude

        Returns:
            Tuple of (should_exclude, reason)
        """
        # Fast path: Check important build files first
        filename = Path(file_path).name
        if filename in cls.IMPORTANT_BUILD_FILES:
            return False, None

        # Normalize path for consistent checking (use forward slashes)
        normalized_path = file_path.replace("\\", "/")

        # Check directory exclusions (optimized with 'any' and generator)
        for excluded_dir in excluded_dirs:
            if f"/{excluded_dir}/" in normalized_path or normalized_path.startswith(
                f"{excluded_dir}/"
            ):
                return True, f"directory: {excluded_dir}"

        # Check pattern exclusions (optimized for common patterns)
        for pattern in excluded_patterns:
            if (
                pattern.startswith("*.") and file_path.endswith(pattern[1:])
            ) or pattern in file_path:
                return True, f"pattern: {pattern}"

        return False, None
