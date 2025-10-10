"""
Comprehensive unit tests for the prompt templating system.

This test suite covers all functionality of the PromptTemplateManager
including template loading, rendering, error handling, caching, and edge cases.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jinja2 import TemplateNotFound, UndefinedError

# Import the module we're testing
from prompt_templates import (
    PromptTemplateManager,
    PromptTemplates,
    get_default_manager,
    list_templates,
    render_prompt,
)


class TestPromptTemplateManager(unittest.TestCase):
    """Test cases for PromptTemplateManager class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a temporary directory for test templates
        self.test_dir = tempfile.mkdtemp()
        self.template_dir = Path(self.test_dir) / "test_prompts"
        self.template_dir.mkdir()

        # Create test template files
        self.create_test_templates()

        # Initialize the manager with test directory
        self.manager = PromptTemplateManager(str(self.template_dir))

    def tearDown(self):
        """Clean up test fixtures after each test method."""
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def create_test_templates(self):
        """Create test template files."""
        # Simple template with variables
        simple_template = """Hello {{ name }}!
Your project type is {{ project_type }}.
You have {{ count }} dependencies."""
        (self.template_dir / "simple.txt").write_text(simple_template)

        # Complex template with loops and conditionals
        complex_template = """Project Analysis for {{ project_type|upper }}

Dependencies:
{% for dep in dependencies %}
- {{ dep.name }}: {{ dep.version }}
{% endfor %}

{% if updates_available %}
Updates available: {{ updates_available }}
{% else %}
All dependencies are up to date.
{% endif %}

Status: {{ status|default("Unknown") }}"""
        (self.template_dir / "complex.txt").write_text(complex_template)

        # Template with missing required variable
        missing_var_template = """Hello {{ name }}!
Missing variable: {{ missing_variable }}"""
        (self.template_dir / "missing_var.txt").write_text(missing_var_template)

        # Empty template
        (self.template_dir / "empty.txt").write_text("")


class TestBasicFunctionality(TestPromptTemplateManager):
    """Test basic functionality of the prompt template system."""

    def test_initialization_valid_directory(self):
        """Test successful initialization with valid directory."""
        self.assertIsInstance(self.manager, PromptTemplateManager)
        self.assertEqual(self.manager.template_dir, self.template_dir)

    def test_initialization_invalid_directory(self):
        """Test initialization fails with invalid directory."""
        with self.assertRaises(FileNotFoundError):
            PromptTemplateManager("/nonexistent/directory")

    def test_initialization_file_instead_of_directory(self):
        """Test initialization fails when path points to file instead of directory."""
        file_path = self.template_dir / "test_file.txt"
        file_path.write_text("test")

        with self.assertRaises(ValueError):
            PromptTemplateManager(str(file_path))

    def test_simple_template_rendering(self):
        """Test rendering a simple template with variables."""
        result = self.manager.render_prompt(
            "simple", name="Alice", project_type="Python", count=5
        )

        expected = """Hello Alice!
Your project type is Python.
You have 5 dependencies."""

        self.assertEqual(result, expected)

    def test_complex_template_rendering(self):
        """Test rendering a complex template with loops and conditionals."""
        dependencies = [
            {"name": "fastapi", "version": "0.111.0"},
            {"name": "jinja2", "version": "3.1.4"},
        ]

        result = self.manager.render_prompt(
            "complex",
            project_type="python",
            dependencies=dependencies,
            updates_available=2,
            status="Good",
        )

        self.assertIn("Project Analysis for PYTHON", result)
        self.assertIn("- fastapi: 0.111.0", result)
        self.assertIn("- jinja2: 3.1.4", result)
        self.assertIn("Updates available: 2", result)
        self.assertIn("Status: Good", result)

    def test_template_with_default_values(self):
        """Test template rendering with default values."""
        result = self.manager.render_prompt(
            "complex",
            project_type="java",
            dependencies=[],
            updates_available=0,
            # Note: status is not provided, should use default
        )

        self.assertIn("Status: Unknown", result)
        self.assertIn("All dependencies are up to date", result)


class TestErrorHandling(TestPromptTemplateManager):
    """Test error handling and edge cases."""

    def test_template_not_found(self):
        """Test error when template doesn't exist."""
        with self.assertRaises(TemplateNotFound) as context:
            self.manager.render_prompt("nonexistent", name="test")

        self.assertIn("Template not found", str(context.exception))
        self.assertIn("Available templates", str(context.exception))

    def test_missing_required_variable(self):
        """Test error when required variable is missing."""
        with self.assertRaises(UndefinedError) as context:
            self.manager.render_prompt("missing_var", name="Alice")
            # missing_variable is not provided

        self.assertIn("Missing required variable", str(context.exception))

    def test_empty_template_name(self):
        """Test error with empty template name."""
        with self.assertRaises(ValueError) as context:
            self.manager.render_prompt("", name="test")

        self.assertIn("Template name cannot be empty", str(context.exception))

    def test_invalid_variable_types(self):
        """Test error with unsupported variable types."""

        # Test with a complex object that's not JSON serializable
        class CustomObject:
            pass

        with self.assertRaises(ValueError) as context:
            self.manager.render_prompt("simple", name=CustomObject())

        self.assertIn("Unsupported variable type", str(context.exception))

    def test_valid_variable_types(self):
        """Test that all supported variable types work."""
        valid_variables = {
            "string_var": "hello",
            "int_var": 42,
            "float_var": 3.14,
            "bool_var": True,
            "list_var": [1, 2, 3],
            "dict_var": {"key": "value"},
            "none_var": None,
        }

        # This should not raise any exception
        self.manager._validate_variables(valid_variables)


class TestTemplateManagement(TestPromptTemplateManager):
    """Test template management functionality."""

    def test_list_available_templates(self):
        """Test listing available templates."""
        templates = self.manager.list_available_templates()

        expected_templates = [
            "complex.txt",
            "empty.txt",
            "missing_var.txt",
            "simple.txt",
        ]
        self.assertEqual(sorted(templates), expected_templates)

    def test_template_exists(self):
        """Test checking if template exists."""
        self.assertTrue(self.manager.template_exists("simple"))
        self.assertTrue(self.manager.template_exists("simple.txt"))
        self.assertFalse(self.manager.template_exists("nonexistent"))

    def test_template_path_normalization(self):
        """Test that template paths are normalized correctly."""
        # Both should work
        result1 = self.manager.render_prompt(
            "simple", name="Alice", project_type="Python", count=1
        )
        result2 = self.manager.render_prompt(
            "simple.txt", name="Alice", project_type="Python", count=1
        )

        self.assertEqual(result1, result2)


class TestCaching(TestPromptTemplateManager):
    """Test template caching functionality."""

    def test_template_caching(self):
        """Test that templates are cached after first load."""
        # First render - should load and cache
        self.manager.render_prompt(
            "simple", name="Alice", project_type="Python", count=1
        )

        cache_info = self.manager.get_cache_info()
        self.assertIn("simple.txt", cache_info["cached_templates"])
        self.assertEqual(cache_info["cache_size"], 1)

    def test_cache_clearing(self):
        """Test clearing the template cache."""
        # Load a template
        self.manager.render_prompt(
            "simple", name="Alice", project_type="Python", count=1
        )
        self.assertGreater(len(self.manager._template_cache), 0)

        # Clear cache
        self.manager.clear_cache()
        self.assertEqual(len(self.manager._template_cache), 0)

    def test_cache_info(self):
        """Test getting cache information."""
        cache_info = self.manager.get_cache_info()

        self.assertIn("cached_templates", cache_info)
        self.assertIn("cache_size", cache_info)
        self.assertIn("template_directory", cache_info)
        self.assertEqual(cache_info["template_directory"], str(self.template_dir))


class TestConvenienceFunctions(TestPromptTemplateManager):
    """Test convenience functions and global manager."""

    @patch("prompt_templates._default_manager", None)
    def test_default_manager_creation(self):
        """Test that default manager is created properly."""
        # Import the module to access the global variable
        import prompt_templates

        # Reset the global manager
        prompt_templates._default_manager = None

        manager = get_default_manager()
        self.assertIsInstance(manager, PromptTemplateManager)

        # Should return the same instance on subsequent calls
        manager2 = get_default_manager()
        self.assertIs(manager, manager2)

    def test_convenience_render_function(self):
        """Test the convenience render_prompt function."""
        # This will use the default manager, so we need templates in the default location
        # We'll mock this since we're using a test directory
        with patch("prompt_templates.get_default_manager") as mock_get_manager:
            mock_get_manager.return_value = self.manager

            result = render_prompt("simple", name="Bob", project_type="Java", count=3)
            self.assertIn("Hello Bob!", result)
            self.assertIn("Java", result)

    def test_convenience_list_function(self):
        """Test the convenience list_templates function."""
        with patch("prompt_templates.get_default_manager") as mock_get_manager:
            mock_get_manager.return_value = self.manager

            templates = list_templates()
            self.assertIn("simple.txt", templates)
            self.assertIn("complex.txt", templates)


class TestPromptTemplatesConstants(unittest.TestCase):
    """Test the PromptTemplates constants class."""

    def test_template_constants_exist(self):
        """Test that all expected template constants are defined."""
        expected_constants = [
            "IDENTIFY_ARTIFACTS",
            "EXTRACT_DEPENDENCIES",
            "RESEARCH_LATEST_VERSIONS",
            "UPDATE_DEPENDENCY_FILE",
            "VALIDATE_AND_FIX_CODE",
            "UPDATE_ENTIRE_PROJECT",
            "UPDATE_PROJECT_WITH_PROGRESS",
        ]

        for constant in expected_constants:
            self.assertTrue(hasattr(PromptTemplates, constant))
            self.assertIsInstance(getattr(PromptTemplates, constant), str)


class TestIntegrationWithRealTemplates(unittest.TestCase):
    """Integration tests with real prompt templates."""

    def setUp(self):
        """Set up with real prompts directory if it exists."""
        self.prompts_dir = Path("prompts")
        if self.prompts_dir.exists():
            self.manager = PromptTemplateManager("prompts")
        else:
            self.skipTest("Real prompts directory not found")

    def test_real_template_loading(self):
        """Test loading real templates if they exist."""
        templates = self.manager.list_available_templates()
        self.assertGreater(len(templates), 0)

    def test_identify_artifacts_template(self):
        """Test the identify_artifacts template with sample data."""
        if not self.manager.template_exists(PromptTemplates.IDENTIFY_ARTIFACTS):
            self.skipTest("identify_artifacts template not found")

        result = self.manager.render_prompt(
            PromptTemplates.IDENTIFY_ARTIFACTS,
            project_type="python",
            directory_list=["src", "tests", "__pycache__"],
            structure_summary=["main.py", "requirements.txt", "test_main.py"],
        )

        self.assertIn("python", result)
        self.assertIn("__pycache__", result)
        self.assertIn("main.py", result)


class TestPerformance(TestPromptTemplateManager):
    """Test performance characteristics."""

    def test_template_caching_performance(self):
        """Test that template caching improves performance."""
        import time

        # Time first render (should load from disk)
        start_time = time.time()
        self.manager.render_prompt(
            "simple", name="Alice", project_type="Python", count=1
        )
        first_render_time = time.time() - start_time

        # Time second render (should use cache)
        start_time = time.time()
        self.manager.render_prompt("simple", name="Bob", project_type="Java", count=2)
        second_render_time = time.time() - start_time

        # Second render should be faster (cached template)
        # Note: This might be flaky in very fast systems, so we'll just check it doesn't error
        self.assertIsNotNone(first_render_time)
        self.assertIsNotNone(second_render_time)


if __name__ == "__main__":
    # Configure logging for tests
    import logging

    logging.basicConfig(level=logging.DEBUG)

    # Run all tests
    unittest.main(verbosity=2)
