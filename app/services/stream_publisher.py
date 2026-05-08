"""
Stream publisher - bridges the agent loop to the SSE endpoint.

The agent loop calls publish_event() to push events onto the task's
asyncio.Queue. The SSE endpoint consumes from the same queue.
"""

import logging

from app.api.stream import get_stream_queue
from app.services.llm.events import AnalysisEvent

logger = logging.getLogger(__name__)


async def publish_event(task_id: str, event: AnalysisEvent) -> None:
    """
    Publish an analysis event to the SSE stream for a task.

    Args:
        task_id: The unique identifier for the running analysis task
        event: The AnalysisEvent to publish
    """
    queue = get_stream_queue(task_id)
    await queue.put(event.to_dict())
    logger.debug("Published %s event for task %s", event.type.value, task_id)


async def complete_stream(task_id: str) -> None:
    """
    Signal that the stream is complete.

    Places a None sentinel on the queue, which causes the SSE
    endpoint to emit a 'complete' event and close the connection.
    """
    queue = get_stream_queue(task_id)
    await queue.put(None)
    logger.debug("Completed stream for task %s", task_id)
