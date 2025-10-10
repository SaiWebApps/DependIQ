"""
Progress API routes for real-time progress tracking
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from ..config import Config
from ..services.progress_service import create_progress_stream

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/progress/{session_id}")
def progress_page(request: Request, session_id: str):
    """Progress page with real-time updates"""
    return templates.TemplateResponse(
        "progress.html", {"request": request, "session_id": session_id}
    )


@router.get("/progress-stream/{session_id}")
def progress_stream(session_id: str):
    """Server-sent events for progress updates"""
    return StreamingResponse(
        create_progress_stream(session_id, Config.MAX_SSE_ITERATIONS),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )
