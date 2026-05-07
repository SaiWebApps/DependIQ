"""
File management API routes for viewing and downloading updated files
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from ..models.project import FileExtensionMap
from ..services.update_service import completed_projects

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/view-file/{session_id}/{file_path:path}")
def view_file(request: Request, session_id: str, file_path: str):
    """View the content of an updated file"""
    if session_id not in completed_projects:
        return {"error": "Session not found or expired"}

    # Decode URL-encoded path
    file_path = file_path.replace("%2F", "/")

    project_data = completed_projects[session_id]
    # Use matched_updates which contains actual project paths
    matched_updates = project_data.get("matched_updates", project_data["updated_files"])

    if file_path not in matched_updates:
        return {
            "error": f"File not found: {file_path}. Available files: {list(matched_updates.keys())[:5]}"
        }

    file_content = matched_updates[file_path]
    project_type = project_data["project_type"]

    # Determine syntax highlighting based on file extension
    extension = os.path.splitext(file_path)[1].lower()
    syntax_language = FileExtensionMap.SYNTAX_LANGUAGE_MAP.get(extension, "text")

    return templates.TemplateResponse(
        "file_viewer.html",
        {
            "request": request,
            "file_path": file_path,
            "session_id": session_id,
            "project_type": project_type,
            "file_content": file_content,
            "syntax_language": syntax_language,
        },
    )


@router.get("/download/{session_id}")
def download_project(session_id: str):
    """Download the updated project"""
    if session_id not in completed_projects:
        return {"error": "Project not found or expired"}

    project_data = completed_projects[session_id]
    file_path = project_data["zip_file"]

    def cleanup():
        try:
            os.unlink(file_path)
            del completed_projects[session_id]
        except:
            pass

    return FileResponse(
        file_path,
        filename="updated_project.zip",
        media_type="application/zip",
        background=BackgroundTask(cleanup),
    )
