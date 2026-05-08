"""
Structured events emitted by the streaming agent loop.

These events allow consumers (WebSocket handlers, SSE endpoints, progress UIs)
to observe the agent's work in real time without coupling to litellm internals.
"""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Types of events emitted during an analysis run."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"


@dataclass
class AnalysisEvent:
    """
    A single event emitted during an agent's streaming execution.

    Event types:
        thinking   — text chunk from the LLM's response
        tool_call  — the agent is invoking a tool
        tool_result — a tool has returned its output
        progress   — phase/percentage update for UI progress bars
        result     — the final structured result of the analysis
        error      — an error occurred during analysis
    """

    type: str  # thinking, tool_call, tool_result, progress, result, error
    content: str | None = None
    name: str | None = None
    input: dict | None = None
    output: str | None = None
    phase: str | None = None
    pct: int | None = None
    data: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict, omitting None fields for cleaner JSON."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def thinking(cls, content: str) -> "AnalysisEvent":
        return cls(type=EventType.THINKING, content=content, data={})

    @classmethod
    def tool_call(cls, name: str, args: dict | None = None) -> "AnalysisEvent":
        return cls(
            type=EventType.TOOL_CALL,
            content=f"Calling {name}",
            data={"name": name, "args": args or {}},
        )

    @classmethod
    def tool_result(cls, name: str, output: str = "") -> "AnalysisEvent":
        return cls(
            type=EventType.TOOL_RESULT,
            content=output or f"{name} complete",
            data={"name": name},
        )

    @classmethod
    def progress(cls, phase: str, pct: int) -> "AnalysisEvent":
        clamped = max(0, min(100, pct))
        return cls(
            type=EventType.PROGRESS,
            content=phase,
            data={"phase": phase, "percent": clamped},
        )

    @classmethod
    def result(cls, content: str, data: dict | None = None) -> "AnalysisEvent":
        return cls(type=EventType.RESULT, content=content, data=data)

    @classmethod
    def error(cls, content: str) -> "AnalysisEvent":
        return cls(type=EventType.ERROR, content=content, data={"error": content})
