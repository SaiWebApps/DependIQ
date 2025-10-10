"""
Progress tracking and Server-Sent Events (SSE) management
"""

import json
import time
from collections.abc import Generator
from typing import Any

# Global progress tracking
progress_status: dict[str, dict[str, Any]] = {}
analysis_status: dict[str, dict[str, Any]] = {}  # For analysis progress tracking


def update_progress(session_id: str, step: str, progress: int, details: str = ""):
    """Update progress for a session"""
    progress_status[session_id] = {
        "step": step,
        "progress": progress,
        "details": details,
        "timestamp": time.time(),
    }


def update_analysis_progress(
    session_id: str, step: str, progress: int, details: str = ""
):
    """Update analysis progress for a session"""
    analysis_status[session_id] = {
        "step": step,
        "progress": progress,
        "details": details,
        "timestamp": time.time(),
    }


def get_progress_status(session_id: str) -> dict[str, Any]:
    """Get progress status for a session"""
    return progress_status.get(session_id, {})


def get_analysis_status(session_id: str) -> dict[str, Any]:
    """Get analysis status for a session"""
    return analysis_status.get(session_id, {})


def create_progress_stream(
    session_id: str, max_iterations: int = 300
) -> Generator[str, None, None]:
    """Create a Server-Sent Events stream for progress updates"""
    iterations = 0

    # Initialize progress if not exists
    if session_id not in progress_status:
        progress_status[session_id] = {
            "step": "Initializing",
            "progress": 0,
            "details": "Starting update process...",
            "timestamp": time.time(),
        }

    while iterations < max_iterations:
        try:
            if session_id in progress_status:
                status = progress_status[session_id]
                yield f"data: {json.dumps(status)}\n\n"

                if status["progress"] >= 100:
                    break
            else:
                yield f"data: {json.dumps({'step': 'Initializing', 'progress': 0, 'details': 'Starting update process...'})}\n\n"

        except Exception as e:
            print(f"📡 SSE ERROR: {e}")
            error_status = {
                "step": "Connection Error",
                "progress": 0,
                "details": f"Stream error: {e!s}",
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(error_status)}\n\n"
            break

        time.sleep(1)
        iterations += 1

    # Timeout fallback
    if iterations >= max_iterations:
        print(f"📡 SSE: Timeout for session {session_id}")
        timeout_status = {
            "step": "Timeout",
            "progress": 0,
            "details": "Process timed out. Please try again.",
            "timestamp": time.time(),
        }
        yield f"data: {json.dumps(timeout_status)}\n\n"


def create_analysis_stream(
    session_id: str, max_iterations: int = 300
) -> Generator[str, None, None]:
    """Create a Server-Sent Events stream for analysis progress updates"""
    iterations = 0

    # Initialize analysis if not exists
    if session_id not in analysis_status:
        analysis_status[session_id] = {
            "step": "Initializing",
            "progress": 0,
            "details": "Starting analysis process...",
            "timestamp": time.time(),
        }

    while iterations < max_iterations:
        try:
            if session_id in analysis_status:
                status = analysis_status[session_id]
                yield f"data: {json.dumps(status)}\n\n"

                # Exit conditions
                if status["progress"] >= 100:
                    print(f"📡 SSE: Analysis complete for session {session_id}")
                    break
                elif status["step"] == "Error" or "Error" in status["step"]:
                    print(f"📡 SSE: Analysis error for session {session_id}")
                    break
            else:
                yield f"data: {json.dumps({'step': 'Waiting', 'progress': 0, 'details': 'Waiting for analysis to start...'})}\n\n"

        except Exception as e:
            print(f"📡 SSE ERROR: {e}")
            error_status = {
                "step": "Connection Error",
                "progress": 0,
                "details": f"Stream error: {e!s}",
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(error_status)}\n\n"
            break

        time.sleep(1)
        iterations += 1

    # Timeout fallback
    if iterations >= max_iterations:
        print(f"📡 SSE: Timeout for session {session_id}")
        timeout_status = {
            "step": "Timeout",
            "progress": 0,
            "details": "Analysis timed out. Please try again.",
            "timestamp": time.time(),
        }
        yield f"data: {json.dumps(timeout_status)}\n\n"


def cleanup_old_sessions(max_age: int = 3600):
    """Clean up sessions older than max_age seconds"""
    current_time = time.time()

    # Clean progress sessions
    expired_progress = [
        session_id
        for session_id, status in progress_status.items()
        if current_time - status.get("timestamp", 0) > max_age
    ]
    for session_id in expired_progress:
        del progress_status[session_id]

    # Clean analysis sessions
    expired_analysis = [
        session_id
        for session_id, status in analysis_status.items()
        if current_time - status.get("timestamp", 0) > max_age
    ]
    for session_id in expired_analysis:
        del analysis_status[session_id]

    if expired_progress or expired_analysis:
        print(
            f"🧹 Cleaned up {len(expired_progress)} progress and {len(expired_analysis)} analysis sessions"
        )


def get_session_count() -> dict[str, int]:
    """Get count of active sessions"""
    return {
        "progress_sessions": len(progress_status),
        "analysis_sessions": len(analysis_status),
        "total_sessions": len(progress_status) + len(analysis_status),
    }
