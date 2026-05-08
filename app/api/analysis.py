"""
Analysis API routes for dependency analysis functionality.

This module is a thin HTTP layer: validate input, dispatch to
analysis_service, return response. All business logic lives in
app/services/analysis_service.py.
"""

import logging
import os
import shutil
import threading
import time

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database import get_db
from ..middleware import get_current_user
from ..models import User
from ..services.analysis_service import run_analysis
from ..services.progress_service import (
    analysis_status,
    create_analysis_stream,
)
from ..services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.post("/analyze/")
async def analyze_dependencies(
    request: Request,
    file: UploadFile = File(...),
    user_instructions: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start analysis of uploaded project ZIP file for dependencies (requires authentication)"""
    if file.filename and not file.filename.endswith(".zip"):
        return {"error": "Please upload a ZIP file"}

    # Create session ID for tracking analysis progress
    session_id = str(int(time.time() * 1000))
    logger.info(
        "UPLOAD: Created session %s for file %s by user %s",
        session_id,
        file.filename,
        current_user.email,
    )

    # Store the uploaded file temporarily
    temp_file_path = Config.get_temp_file_path(session_id)

    try:
        with open(temp_file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(
            "UPLOAD: Successfully saved %d bytes", os.path.getsize(temp_file_path)
        )
    except Exception as e:
        logger.error("UPLOAD: Error saving file: %s", e)
        return {"error": f"Failed to save uploaded file: {e!s}"}

    # Create project history entry
    user_service = UserService(db)
    project_name = (
        file.filename.replace(".zip", "") if file.filename else "Uploaded Project"
    )
    await user_service.create_project_history(
        user_id=str(current_user.id),
        session_id=session_id,
        project_name=project_name,
        source_type="zip_upload",
        zip_file_path=temp_file_path,
    )
    logger.info("HISTORY: Created project history entry for session %s", session_id)

    # Store file info for the analysis process
    analysis_status[session_id] = {
        "temp_file_path": temp_file_path,
        "filename": file.filename,
        "status": "queued",
        "user_instructions": user_instructions.strip() if user_instructions else "",
        "user_id": str(current_user.id),
    }

    # Redirect to the analysis page with session_id in URL
    return RedirectResponse(url=f"/api/analysis/{session_id}", status_code=302)


@router.get("/analysis/{session_id}")
def analysis_page(request: Request, session_id: str):
    """Analysis progress page with real-time updates"""
    return templates.TemplateResponse(
        "analysis.html", {"request": request, "session_id": session_id}
    )


@router.get("/analysis-stream/{session_id}")
def analysis_stream(session_id: str):
    """Server-sent events for analysis progress updates"""
    return StreamingResponse(
        create_analysis_stream(session_id, Config.MAX_SSE_ITERATIONS),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/start-analysis/{session_id}")
async def start_analysis(session_id: str):
    """Start the analysis process in a background thread"""
    logger.info("START-ANALYSIS: Request to start analysis for session %s", session_id)

    if session_id not in analysis_status:
        logger.error("START-ANALYSIS: Session %s not found!", session_id)
        return {"success": False, "error": f"Session {session_id} not found"}

    thread = threading.Thread(target=run_analysis, args=(session_id,), daemon=True)
    thread.start()
    logger.info("START-ANALYSIS: Analysis thread started for session %s", session_id)

    return {"success": True, "message": "Analysis started"}


@router.get("/analysis-results/{session_id}")
def analysis_results(request: Request, session_id: str):
    """Show analysis results"""
    if (
        session_id not in analysis_status
        or "results" not in analysis_status[session_id]
    ):
        return {"error": "Analysis not found or not completed"}

    results = analysis_status[session_id]["results"]
    dependencies = results["dependencies"]
    project_type = results["project_type"]
    update_session_id = results["update_session_id"]

    # Generate HTML response
    dep_rows = ""
    updates_available = 0
    for dep in dependencies:
        if dep["current_version"] != dep["latest_version"]:
            status = '<span class="status-chip status-update">Update available</span>'
            status_class = "update-available"
            updates_available += 1
        else:
            status = '<span class="status-chip status-current">Up to date</span>'
            status_class = "up-to-date"

        dep_rows += f"""
        <tr class="{status_class}">
            <td>
                <div class="dep-name">{dep["name"]}</div>
                <div class="dep-description">{dep["description"]}</div>
            </td>
            <td class="current">{dep["current_version"]}</td>
            <td class="latest">{dep["latest_version"]}</td>
            <td>{status}</td>
        </tr>
        """

    update_form = ""
    if updates_available > 0:
        update_form = f"""
        <div class="update-section">
            <h3 style="margin-top: 0; color: #1976d2;">
                <span class="material-icons" style="vertical-align: middle; margin-right: 8px;">rocket_launch</span>
                Ready to Update
            </h3>
            <p style="color: #666; margin-bottom: 24px;">{updates_available} dependencies can be updated to newer versions with AI-powered compatibility fixes.</p>
            <a href="/progress/{update_session_id}" class="update-btn">
                <span class="material-icons">psychology</span>
                AI Update All Dependencies & Code
            </a>
        </div>
        """

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "project_type": project_type,
            "dependencies": dependencies,
            "updates_available": updates_available,
            "dep_rows": dep_rows,
            "update_form": update_form,
        },
    )
