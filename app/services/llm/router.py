"""
Model routing by task type with failover.

Routes LLM requests to the appropriate model based on task complexity,
cost sensitivity, and privacy requirements. Supports failover chains
when a provider is unavailable.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(Enum):
    """Categories of work the agent can do, ordered by complexity."""

    MANIFEST_PARSE = "manifest_parse"
    DEPENDENCY_EXTRACT = "dependency_extract"
    VERSION_RESEARCH = "version_research"
    CHANGELOG_SUMMARY = "changelog_summary"
    SECURITY_ANALYSIS = "security_analysis"
    MIGRATION_PLANNING = "migration_planning"
    CODE_UPDATE = "code_update"


class RoutingMode(Enum):
    """How aggressive to be with cost optimization."""

    QUALITY = "quality"
    BALANCED = "balanced"
    COST = "cost"
    LOCAL_ONLY = "local_only"


@dataclass
class ModelConfig:
    """Configuration for a single model endpoint."""

    model_id: str
    provider: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0
    supports_tools: bool = True

    @property
    def litellm_model(self) -> str:
        """Model string in litellm format (provider/model)."""
        if self.provider:
            return f"{self.provider}/{self.model_id}"
        return self.model_id


DEFAULT_ROUTES: dict[TaskType, list[str]] = {
    TaskType.MANIFEST_PARSE: [
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
        "ollama/qwen2.5-coder:7b",
    ],
    TaskType.DEPENDENCY_EXTRACT: [
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
        "ollama/qwen2.5-coder:7b",
    ],
    TaskType.VERSION_RESEARCH: [
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    TaskType.CHANGELOG_SUMMARY: [
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
        "ollama/llama3.1:8b",
    ],
    TaskType.SECURITY_ANALYSIS: [
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    TaskType.MIGRATION_PLANNING: [
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
    ],
    TaskType.CODE_UPDATE: [
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
    ],
}

LOCAL_ONLY_ROUTES: dict[TaskType, list[str]] = {
    TaskType.MANIFEST_PARSE: ["ollama/qwen2.5-coder:7b", "ollama/llama3.1:8b"],
    TaskType.DEPENDENCY_EXTRACT: [
        "ollama/qwen2.5-coder:7b",
        "ollama/deepseek-coder-v2:16b",
    ],
    TaskType.VERSION_RESEARCH: [
        "ollama/deepseek-coder-v2:16b",
        "ollama/qwen2.5-coder:14b",
    ],
    TaskType.CHANGELOG_SUMMARY: ["ollama/llama3.1:8b", "ollama/qwen2.5-coder:7b"],
    TaskType.SECURITY_ANALYSIS: [
        "ollama/deepseek-coder-v2:16b",
        "ollama/qwen2.5-coder:14b",
    ],
    TaskType.MIGRATION_PLANNING: [
        "ollama/deepseek-coder-v2:16b",
        "ollama/qwen2.5-coder:14b",
    ],
    TaskType.CODE_UPDATE: ["ollama/deepseek-coder-v2:16b", "ollama/qwen2.5-coder:14b"],
}

COST_ROUTES: dict[TaskType, list[str]] = {
    TaskType.MANIFEST_PARSE: [
        "ollama/qwen2.5-coder:7b",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    TaskType.DEPENDENCY_EXTRACT: [
        "ollama/qwen2.5-coder:7b",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    TaskType.VERSION_RESEARCH: [
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
    ],
    TaskType.CHANGELOG_SUMMARY: [
        "ollama/llama3.1:8b",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    TaskType.SECURITY_ANALYSIS: [
        "anthropic/claude-haiku-4-5-20251001",
        "anthropic/claude-sonnet-4-20250514",
    ],
    TaskType.MIGRATION_PLANNING: [
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
    ],
    TaskType.CODE_UPDATE: [
        "anthropic/claude-haiku-4-5-20251001",
        "anthropic/claude-sonnet-4-20250514",
    ],
}


@dataclass
class ModelRouter:
    """
    Routes tasks to appropriate models based on task type and routing mode.
    Provides failover chains so if model A is unavailable, we try model B.
    """

    mode: RoutingMode = field(
        default_factory=lambda: RoutingMode(
            os.getenv("DEPENDIQ_ROUTING_MODE", "balanced")
        )
    )
    custom_routes: dict[TaskType, list[str]] = field(default_factory=dict)

    def get_model_chain(self, task: TaskType) -> list[str]:
        """Get the ordered list of models to try for a given task."""
        if self.custom_routes and task in self.custom_routes:
            return self.custom_routes[task]

        route_table = {
            RoutingMode.QUALITY: DEFAULT_ROUTES,
            RoutingMode.BALANCED: DEFAULT_ROUTES,
            RoutingMode.COST: COST_ROUTES,
            RoutingMode.LOCAL_ONLY: LOCAL_ONLY_ROUTES,
        }

        table = route_table.get(self.mode, DEFAULT_ROUTES)
        return table.get(task, DEFAULT_ROUTES[task])

    def get_primary_model(self, task: TaskType) -> str:
        """Get the first-choice model for a task."""
        chain = self.get_model_chain(task)
        return chain[0] if chain else "anthropic/claude-sonnet-4-20250514"

    def get_fallbacks(self, task: TaskType) -> list[str]:
        """Get fallback models (everything after primary)."""
        chain = self.get_model_chain(task)
        return chain[1:] if len(chain) > 1 else []

    def get_config(self, task: TaskType) -> dict[str, Any]:
        """Get full litellm-compatible config for a task (with fallbacks)."""
        chain = self.get_model_chain(task)
        primary = chain[0] if chain else "anthropic/claude-sonnet-4-20250514"
        fallbacks = chain[1:] if len(chain) > 1 else []

        return {
            "model": primary,
            "fallbacks": fallbacks,
            "temperature": 0.0,
            "max_tokens": self._max_tokens_for_task(task),
        }

    def _max_tokens_for_task(self, task: TaskType) -> int:
        heavy_tasks = {TaskType.CODE_UPDATE, TaskType.MIGRATION_PLANNING}
        medium_tasks = {TaskType.SECURITY_ANALYSIS, TaskType.VERSION_RESEARCH}

        if task in heavy_tasks:
            return 8192
        elif task in medium_tasks:
            return 4096
        return 2048

    def available_providers(self) -> list[str]:
        """List which providers have API keys configured."""
        providers = []
        if os.getenv("ANTHROPIC_API_KEY"):
            providers.append("anthropic")
        if os.getenv("OPENAI_API_KEY"):
            providers.append("openai")
        # Ollama is always "available" (local, no key needed)
        providers.append("ollama")
        return providers

    def filter_chain_by_available(self, task: TaskType) -> list[str]:
        """Filter model chain to only include providers with keys configured."""
        available = self.available_providers()
        chain = self.get_model_chain(task)
        return [m for m in chain if any(m.startswith(p) for p in available)]
