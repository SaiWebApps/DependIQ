"""
Task-specific prompt loading for the DependIQ agent.

Loads Jinja2 markdown templates from app/services/llm/prompts/ and renders
them with task-specific variables. This replaces the hardcoded SYSTEM_PROMPT
for tasks that have specialized templates.
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

logger = logging.getLogger(__name__)

# Template directory lives alongside this module
_TEMPLATE_DIR = Path(__file__).parent / "prompts"


class TaskPromptManager:
    """
    Manages task-specific prompt templates for the agent.

    Templates are markdown files with Jinja2 variables (e.g., {{project_name}}).
    Falls back to a generic system prompt if no task-specific template exists.
    """

    GENERIC_SYSTEM_PROMPT = (
        "You are DependIQ, a dependency intelligence agent. "
        "You have tools to look up real package versions from registries. "
        "Always use your tools to check actual versions — never guess from memory. "
        "Return structured JSON when asked."
    )

    def __init__(self, template_dir: Path | None = None):
        """
        Initialize the prompt manager.

        Args:
            template_dir: Directory containing .md template files.
                          Defaults to app/services/llm/prompts/
        """
        self.template_dir = template_dir or _TEMPLATE_DIR

        if not self.template_dir.exists():
            logger.warning(
                f"Template directory does not exist: {self.template_dir}. "
                "Will use generic system prompt for all tasks."
            )
            self.env = None
            return

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, **variables: Any) -> str:
        """
        Render a task-specific prompt template.

        Args:
            template_name: Template name without extension (e.g., 'extract_dependencies')
            **variables: Jinja2 template variables

        Returns:
            Rendered prompt string, or the generic system prompt if template not found
        """
        if self.env is None:
            return self.GENERIC_SYSTEM_PROMPT

        filename = f"{template_name}.md"
        try:
            template = self.env.get_template(filename)
            rendered = template.render(**variables)
            return rendered.strip()
        except TemplateNotFound:
            logger.debug(f"No template '{filename}' found, using generic system prompt")
            return self.GENERIC_SYSTEM_PROMPT

    def has_template(self, template_name: str) -> bool:
        """Check if a task-specific template exists."""
        if self.env is None:
            return False
        filename = f"{template_name}.md"
        full_path = self.template_dir / filename
        return full_path.exists()

    def list_templates(self) -> list[str]:
        """List all available template names (without extension)."""
        if not self.template_dir.exists():
            return []
        return sorted(p.stem for p in self.template_dir.glob("*.md"))


# Module-level singleton
_default_manager: TaskPromptManager | None = None


def get_task_prompt_manager() -> TaskPromptManager:
    """Get or create the singleton TaskPromptManager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = TaskPromptManager()
    return _default_manager
