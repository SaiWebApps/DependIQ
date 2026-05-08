"""
Stream publisher - bridges the agent loop to the SSE endpoint.

The agent loop calls publish_event() to push events onto the task's
asyncio.Queue. The SSE endpoint consumes from the same queue.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from app.api.stream import _streams, get_stream_queue
from app.services.llm.events import AnalysisEvent

logger = logging.getLogger(__name__)


def create_stream(task_id: str) -> None:
    """Create a stream queue for a task (idempotent)."""
    get_stream_queue(task_id)


def get_active_streams() -> set[str]:
    """Return IDs of currently active streams."""
    return set(_streams.keys())


async def publish_event(task_id: str, event: AnalysisEvent) -> None:
    """Publish an analysis event to the SSE stream for a task."""
    queue = get_stream_queue(task_id)
    await queue.put(event.to_dict())
    logger.debug("Published %s event for task %s", event.type, task_id)


async def complete_stream(task_id: str) -> None:
    """Signal that the stream is complete (None sentinel)."""
    queue = get_stream_queue(task_id)
    await queue.put(None)
    logger.debug("Completed stream for task %s", task_id)


async def subscribe(task_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to a task's event stream. Yields SSE-formatted lines."""
    if task_id not in _streams:
        yield "event: error\ndata: {\"type\": \"error\", \"content\": \"Stream not found\"}\n\n"
        return
    queue = _streams[task_id]
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
        except TimeoutError:
            yield ": keepalive\n\n"
            continue
        if event is None:
            yield "event: complete\ndata: {}\n\n"
            break
        event_type = event.get("type", "message")
        yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"


def cleanup_stream(task_id: str) -> None:
    """Remove a stream queue."""
    _streams.pop(task_id, None)
