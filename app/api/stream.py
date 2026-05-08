"""
SSE streaming endpoint for real-time analysis events.

Uses asyncio.Queue for in-memory pub/sub between the agent loop
(producer) and the SSE endpoint (consumer). Each task_id gets its
own queue that lives for the duration of the analysis.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

# In-memory store of active analysis streams (task_id -> asyncio.Queue)
_streams: dict[str, asyncio.Queue] = {}


def get_stream_queue(task_id: str) -> asyncio.Queue:
    """Get or create a queue for a task's events."""
    if task_id not in _streams:
        _streams[task_id] = asyncio.Queue()
    return _streams[task_id]


def cleanup_stream(task_id: str) -> None:
    """Remove stream queue when analysis completes."""
    _streams.pop(task_id, None)


def has_stream(task_id: str) -> bool:
    """Check if a stream exists for a task."""
    return task_id in _streams


def _render_event_html(event: dict) -> str:
    """
    Render an event dict as an HTML fragment for HTMX SSE swap.

    Each event type produces a small HTML snippet that HTMX inserts
    into the appropriate target div.
    """
    event_type = event.get("type", "")
    content = event.get("content", "")
    data = event.get("data", {})

    if event_type == "thinking":
        return f'<p class="text-slate-300 text-sm">{_escape(content)}</p>'

    elif event_type == "tool_call":
        name = _escape(data.get("name", "unknown"))
        return (
            f'<div class="flex items-center gap-2 text-xs text-slate-400">'
            f'<span class="text-indigo-400">&#9654;</span> Calling {name}...</div>'
        )

    elif event_type == "tool_result":
        name = _escape(data.get("name", "unknown"))
        return (
            f'<div class="flex items-center gap-2 text-xs text-emerald-400">'
            f'<span>&#10003;</span> {name} complete</div>'
        )

    elif event_type == "progress":
        phase = _escape(data.get("phase", ""))
        percent = data.get("percent", 0)
        # Return JSON that the frontend JS uses to update the progress bar
        return json.dumps({"phase": phase, "percent": percent})

    elif event_type == "result":
        return (
            f'<div class="bg-slate-800 rounded-lg p-4 border border-emerald-700">'
            f'<h3 class="text-emerald-400 text-sm font-medium mb-2">Analysis Complete</h3>'
            f'<div class="text-slate-300 text-sm whitespace-pre-wrap">{_escape(content)}</div>'
            f'</div>'
        )

    elif event_type == "error":
        return (
            f'<div class="bg-red-900/20 rounded-lg p-4 border border-red-700">'
            f'<h3 class="text-red-400 text-sm font-medium mb-2">Error</h3>'
            f'<div class="text-red-300 text-sm">{_escape(content)}</div>'
            f'</div>'
        )

    return ""


def _escape(text: str) -> str:
    """Basic HTML escaping for user content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@router.get("/{task_id}")
async def stream_analysis(task_id: str, request: Request):
    """
    SSE endpoint that streams AnalysisEvents for a running task.

    Events are formatted as:
        event: {type}
        data: {json}

    A keepalive comment is sent every 30s to prevent proxy timeouts.
    The stream ends when a None sentinel is placed on the queue.
    """
    queue = get_stream_queue(task_id)

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except TimeoutError:
                    # Send keepalive comment to prevent proxy timeouts
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    # Sentinel: stream complete
                    yield "event: complete\ndata: {}\n\n"
                    break

                # Emit the raw JSON event
                event_json = json.dumps(event)
                event_type = event.get("type", "message")
                yield f"event: {event_type}\ndata: {event_json}\n\n"

                # Also emit rendered HTML for HTMX consumers
                html = _render_event_html(event)
                if html:
                    yield f"event: {event_type}_html\ndata: {json.dumps({'html': html})}\n\n"

        finally:
            cleanup_stream(task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
