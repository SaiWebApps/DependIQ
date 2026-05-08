"""
Structured events emitted by the streaming agent loop.

These events allow consumers (WebSocket handlers, SSE endpoints, progress UIs)
to observe the agent's work in real time without coupling to litellm internals.
"""

from dataclasses import asdict, dataclass
from typing import Any


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
    """

    type: str  # thinking, tool_call, tool_result, progress, result
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
