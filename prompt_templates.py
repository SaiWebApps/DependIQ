"""
Prompt Template Management System using Jinja2

This module provides a robust system for loading and rendering ChatGPT prompts
from template files with proper variable substitution, error handling, and caching.
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    Template,
    TemplateNotFound,
    UndefinedError,
)

# Configure logging for the module
logger = logging.getLogger(__name__)


class PromptTemplateManager:
    """
    Manages loading and rendering of ChatGPT prompt templates using Jinja2.

    Features:
    - Jinja2 template engine for powerful templating
    - Template caching for performance
    - Comprehensive error handling
    - Configurable template directory
    - Input validation
    """

    def __init__(self, template_dir: str = "prompts"):
        """
        Initialize the PromptTemplateManager.

        Args:
            template_dir: Directory containing template files (default: "prompts")
        """
        self.template_dir = Path(template_dir)
        self._validate_template_directory()

        # Initialize Jinja2 environment
        from jinja2 import StrictUndefined

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,  # Raise errors for undefined variables
        )

        # Template cache for performance
        self._template_cache: dict[str, Template] = {}

        logger.info(
            f"PromptTemplateManager initialized with template directory: {self.template_dir}"
        )

    def _validate_template_directory(self) -> None:
        """Validate that the template directory exists and is accessible."""
        if not self.template_dir.exists():
            raise FileNotFoundError(
                f"Template directory does not exist: {self.template_dir}"
            )

        if not self.template_dir.is_dir():
            raise ValueError(f"Template path is not a directory: {self.template_dir}")

    def _get_template_path(self, template_name: str) -> str:
        """
        Get the full template file path.

        Args:
            template_name: Name of the template (with or without .txt extension)

        Returns:
            Template filename with .txt extension
        """
        if not template_name.endswith(".txt"):
            template_name += ".txt"
        return template_name

    def _load_template(self, template_name: str) -> Template:
        """
        Load a template from file, with caching.

        Args:
            template_name: Name of the template file

        Returns:
            Compiled Jinja2 template

        Raises:
            TemplateNotFound: If template file doesn't exist
        """
        template_path = self._get_template_path(template_name)

        # Check cache first
        if template_path in self._template_cache:
            return self._template_cache[template_path]

        try:
            template = self.env.get_template(template_path)
            self._template_cache[template_path] = template
            logger.debug(f"Loaded and cached template: {template_path}")
            return template
        except TemplateNotFound:
            available_templates = self.list_available_templates()
            error_msg = f"Template not found: {template_path}. Available templates: {available_templates}"
            logger.error(error_msg)
            raise TemplateNotFound(error_msg)

    def render_prompt(self, template_name: str, **variables) -> str:
        """
        Render a prompt template with the given variables.

        Args:
            template_name: Name of the template to render
            **variables: Variables to substitute in the template

        Returns:
            Rendered prompt string

        Raises:
            TemplateNotFound: If template doesn't exist
            UndefinedError: If required variables are missing
            ValueError: If variables contain invalid types
        """
        if not template_name:
            raise ValueError("Template name cannot be empty")

        # Validate variable types
        self._validate_variables(variables)

        try:
            template = self._load_template(template_name)
            rendered = template.render(**variables)

            logger.debug(
                f"Successfully rendered template '{template_name}' with {len(variables)} variables"
            )
            return rendered.strip()

        except UndefinedError as e:
            error_msg = (
                f"Missing required variable in template '{template_name}': {e!s}"
            )
            logger.error(error_msg)
            raise UndefinedError(error_msg)
        except Exception as e:
            error_msg = f"Error rendering template '{template_name}': {e!s}"
            logger.error(error_msg)
            raise

    def _validate_variables(self, variables: dict[str, Any]) -> None:
        """
        Validate that all variables are of acceptable types.

        Args:
            variables: Dictionary of template variables

        Raises:
            ValueError: If variables contain unsupported types
        """
        supported_types = (str, int, float, bool, list, dict, type(None))

        for key, value in variables.items():
            if not isinstance(value, supported_types):
                raise ValueError(
                    f"Unsupported variable type for '{key}': {type(value)}. "
                    f"Supported types: {[t.__name__ for t in supported_types]}"
                )

    def list_available_templates(self) -> list[str]:
        """
        List all available template files.

        Returns:
            List of template filenames
        """
        try:
            templates = []
            for file_path in self.template_dir.glob("*.txt"):
                templates.append(file_path.name)
            return sorted(templates)
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []

    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template exists.

        Args:
            template_name: Name of the template to check

        Returns:
            True if template exists, False otherwise
        """
        template_path = self._get_template_path(template_name)
        full_path = self.template_dir / template_path
        return full_path.exists()

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._template_cache.clear()
        logger.info("Template cache cleared")

    def get_cache_info(self) -> dict[str, Any]:
        """
        Get information about the template cache.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_templates": list(self._template_cache.keys()),
            "cache_size": len(self._template_cache),
            "template_directory": str(self.template_dir),
        }


# Global instance for easy access
_default_manager: PromptTemplateManager | None = None


def get_default_manager() -> PromptTemplateManager:
    """
    Get the default PromptTemplateManager instance.

    Returns:
        Default PromptTemplateManager instance
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = PromptTemplateManager()
    return _default_manager


def render_prompt(template_name: str, **variables) -> str:
    """
    Convenience function to render a prompt using the default manager.

    Args:
        template_name: Name of the template to render
        **variables: Variables to substitute in the template

    Returns:
        Rendered prompt string
    """
    return get_default_manager().render_prompt(template_name, **variables)


def list_templates() -> list[str]:
    """
    Convenience function to list available templates using the default manager.

    Returns:
        List of available template names
    """
    return get_default_manager().list_available_templates()


# Predefined template names for type safety and IDE support
class PromptTemplates:
    """Constants for available prompt template names."""

    IDENTIFY_ARTIFACTS = "identify_artifacts"
    EXTRACT_DEPENDENCIES = "extract_dependencies"
    RESEARCH_LATEST_VERSIONS = "research_latest_versions"
    UPDATE_DEPENDENCY_FILE = "update_dependency_file"
    VALIDATE_AND_FIX_CODE = "validate_and_fix_code"
    UPDATE_ENTIRE_PROJECT = "update_entire_project"
    UPDATE_PROJECT_WITH_PROGRESS = "update_project_with_progress"
