"""
Provider-agnostic LLM agent layer for DependIQ.

Architecture:
- tools.py: Tool definitions + executors (registry lookups, web_fetch)
- router.py: Model routing by task type + failover
- agent.py: The agentic loop (tool_use -> execute -> feed back -> repeat)
- events.py: Structured events for streaming agent observation
"""

from .agent import Agent, AgentResult
from .events import AnalysisEvent
from .router import ModelRouter, RoutingMode, TaskType
from .tools import ToolRegistry, create_default_registry

__all__ = [
    "Agent",
    "AgentResult",
    "AnalysisEvent",
    "ModelRouter",
    "RoutingMode",
    "TaskType",
    "ToolRegistry",
    "create_default_registry",
]
