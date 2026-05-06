"""
Provider-agnostic LLM agent layer for DependIQ.

Architecture:
- tools.py: Tool definitions + executors (registry lookups, web_fetch)
- router.py: Model routing by task type + failover
- agent.py: The agentic loop (tool_use -> execute -> feed back -> repeat)
"""

from .agent import Agent, AgentResult
from .router import ModelRouter, RoutingMode, TaskType
from .tools import ToolRegistry, create_default_registry

__all__ = [
    "Agent",
    "AgentResult",
    "ModelRouter",
    "RoutingMode",
    "TaskType",
    "ToolRegistry",
    "create_default_registry",
]
