"""
Updates API routes for project dependency updates and code fixes.

This module is a thin HTTP layer: validate input, dispatch to update_service,
return response. All business logic lives in app/services/update_service.py.
"""

import json
import logging
import os
import tempfile
import threading
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..models.dependency import Dependency
from ..models.exclusions import ArtifactExclusionConfig
from ..services.dependency_agent import update_entire_project_with_gpt
from ..services.update_service import run_update

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/update/")
async def update_project(request: Request):
    """Legacy update endpoint (kept for compatibility)"""
    form = await request.form()
    data_file = form.get("data_file")

    if not data_file or not isinstance(data_file, str) or not os.path.exists(data_file):
        return {"error": "Session expired. Please analyze the project again."}

    with open(data_file) as f:
        data = json.load(f)
    os.unlink(data_file)

    dependencies = [Dependency(**dep_data) for dep_data in data["dependencies"]]
    project_files = data["project_files"]

    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_output.close()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            updated_files = update_entire_project_with_gpt(
                data["project_type"], project_files, dependencies, data["dep_file_name"]
            )

            # Recreate the entire project structure
            for file_path, content in project_files.items():
                full_path = os.path.join(tmpdir, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                if file_path in updated_files:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(updated_files[file_path])
                elif isinstance(content, str):
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                else:
                    with open(full_path, "wb") as f:
                        f.write(bytes.fromhex(content))

            # Create ZIP applying exclusion rules via ArtifactExclusionConfig
            exclusion_analysis = data.get("exclusion_analysis", {})
            excluded_dirs = set(exclusion_analysis.get("excluded_directories", []))
            excluded_patterns = set(exclusion_analysis.get("excluded_patterns", []))

            with zipfile.ZipFile(
                temp_output.name, "w", zipfile.ZIP_DEFLATED
            ) as zip_out:
                for root, dirs, files in os.walk(tmpdir):
                    dirs[:] = [d for d in dirs if d not in excluded_dirs]

                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, tmpdir)

                        should_exclude, _reason = (
                            ArtifactExclusionConfig.should_exclude_file(
                                rel_path, excluded_dirs, excluded_patterns
                            )
                        )
                        if not should_exclude:
                            zip_out.write(full_path, rel_path)

        def cleanup():
            try:
                os.unlink(temp_output.name)
            except OSError:
                pass

        return FileResponse(
            temp_output.name,
            filename="updated_project.zip",
            media_type="application/zip",
            background=BackgroundTask(cleanup),
        )

    except Exception as e:
        try:
            os.unlink(temp_output.name)
        except OSError:
            pass
        return {"error": f"Update failed: {e!s}"}


@router.post("/start-update/{session_id}")
async def start_update(session_id: str):
    """Start the project update process in a background thread"""
    thread = threading.Thread(target=run_update, args=(session_id,), daemon=True)
    thread.start()
    return {"success": True, "message": "Update started"}
