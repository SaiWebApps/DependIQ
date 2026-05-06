"""
Analysis API routes for dependency analysis functionality
"""

import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database import AsyncSessionLocal, get_db
from ..middleware import get_current_user
from ..models import User
from ..services.ai_service import (
    extract_dependencies_with_gpt,
    identify_artifacts_with_gpt,
)
from ..services.dependency_agent import research_latest_versions
from ..services.progress_service import (
    analysis_status,
    create_analysis_stream,
    update_analysis_progress,
)
from ..services.user_service import UserService
from ..utils.project_utils import collect_sbt_files, detect_project_type

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
    print(
        f"🔧 UPLOAD: Created session {session_id} for file {file.filename} by user {current_user.email}"
    )

    # Store the uploaded file temporarily
    temp_file_path = Config.get_temp_file_path(session_id)
    print(f"🔧 UPLOAD: Saving to temp file: {temp_file_path}")

    try:
        with open(temp_file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        print(f"🔧 UPLOAD: Successfully saved {os.path.getsize(temp_file_path)} bytes")
    except Exception as e:
        print(f"❌ UPLOAD: Error saving file: {e}")
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
    print(f"📊 HISTORY: Created project history entry for session {session_id}")

    # Store file info for the analysis process
    analysis_status[session_id] = {
        "temp_file_path": temp_file_path,
        "filename": file.filename,
        "status": "queued",
        "user_instructions": user_instructions.strip() if user_instructions else "",
        "user_id": str(current_user.id),
    }
    print(f"🔧 UPLOAD: Stored session data: {analysis_status[session_id]}")
    if user_instructions:
        print(f"📝 USER INSTRUCTIONS: {user_instructions[:100]}...")
    print(f"📊 UPLOAD: Total sessions: {len(analysis_status)}")

    # Redirect to the analysis page with session_id in URL
    return RedirectResponse(url=f"/api/analysis/{session_id}", status_code=302)


def analyze_dependencies_with_progress(session_id: str):
    """Analyze dependencies with progress tracking"""
    try:
        print(f"🔍 ANALYSIS: Starting analysis for session {session_id}")
        print(f"🔍 ANALYSIS: Available sessions: {list(analysis_status.keys())}")

        if session_id not in analysis_status:
            update_analysis_progress(session_id, "Error", 0, "Session not found")
            print(f"❌ ANALYSIS: Session {session_id} not found in analysis_status")
            return

        file_info = analysis_status[session_id]
        print(f"🔍 ANALYSIS: Session data: {file_info}")

        if "temp_file_path" not in file_info:
            update_analysis_progress(
                session_id,
                "Error",
                0,
                "Session data incomplete - missing temp_file_path",
            )
            print(f"❌ ANALYSIS: temp_file_path missing from session {session_id}")
            return

        temp_file_path = file_info["temp_file_path"]
        print(f"🔍 ANALYSIS: Using temp file: {temp_file_path}")

        # Check if temp file exists
        if not os.path.exists(temp_file_path):
            update_analysis_progress(
                session_id, "Error", 0, f"Uploaded file not found: {temp_file_path}"
            )
            print(f"❌ ANALYSIS: Temp file not found: {temp_file_path}")
            return

        update_analysis_progress(
            session_id, "Extracting project files", 10, "Reading uploaded ZIP file..."
        )
        time.sleep(0.5)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract uploaded file
            with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            update_analysis_progress(
                session_id,
                "Detecting project type",
                20,
                "Scanning for dependency files...",
            )
            time.sleep(0.5)

            # Detect project type
            project_type, dep_file_path, dep_file_name = detect_project_type(tmpdir)
            if project_type == "unknown":
                update_analysis_progress(
                    session_id,
                    "Error",
                    0,
                    "Unsupported project type. Supported: requirements.txt, pom.xml, build.gradle, build.sbt",
                )
                return

            update_analysis_progress(
                session_id, "Reading dependency files", 30, f"Found {dep_file_name}"
            )
            time.sleep(0.5)

            # For SBT projects, collect all related files for comprehensive analysis
            if project_type == "sbt":
                update_analysis_progress(
                    session_id,
                    "Collecting SBT files",
                    35,
                    "Gathering build.sbt, project/build.properties, and project/plugins.sbt files...",
                )
                time.sleep(0.5)

                sbt_files = collect_sbt_files(tmpdir)
                print(
                    f"🔍 SBT FILES: Collected {len(sbt_files)} SBT-related files: {list(sbt_files.keys())}"
                )

                # Combine all SBT files for analysis
                combined_content = ""
                for file_path, content in sbt_files.items():
                    combined_content += f"\n=== {file_path} ===\n{content}\n"

                file_content = combined_content
                dep_file_name = f"SBT project files ({len(sbt_files)} files)"
            else:
                # Read single dependency file for other project types
                with open(dep_file_path, encoding="utf-8") as f:
                    file_content = f.read()

            update_analysis_progress(
                session_id,
                "Extracting dependencies with AI",
                45,
                "ChatGPT is parsing your dependency files...",
            )
            time.sleep(1)

            # Use ChatGPT to extract all dependencies
            dependencies = extract_dependencies_with_gpt(
                project_type, file_content, dep_file_name
            )
            if not dependencies:
                update_analysis_progress(
                    session_id,
                    "Error",
                    0,
                    f"ChatGPT could not extract dependencies from {dep_file_name}",
                )
                return

            update_analysis_progress(
                session_id,
                "Researching latest versions",
                70,
                f"AI is researching latest versions for {len(dependencies)} dependencies...",
            )
            time.sleep(1)

            # Research latest versions using agent with live registry lookups
            dependencies = research_latest_versions(dependencies, project_type)

            update_analysis_progress(
                session_id,
                "Preparing project analysis",
                85,
                "Collecting project files for intelligent filtering...",
            )
            time.sleep(0.5)

            try:
                # First, collect ALL project files for ChatGPT analysis
                all_project_files = {}
                print(f"📁 COLLECTING: Starting file collection from {tmpdir}")

                for root, _, files in os.walk(tmpdir):
                    for f in files:
                        if not f.endswith(".zip"):  # Skip uploaded zip only
                            full_path = os.path.join(root, f)
                            rel_path = os.path.relpath(full_path, tmpdir)
                            try:
                                with open(full_path, encoding="utf-8") as file_handle:
                                    all_project_files[rel_path] = file_handle.read()
                            except:
                                # Handle binary files
                                try:
                                    with open(full_path, "rb") as file_handle:
                                        all_project_files[
                                            rel_path
                                        ] = file_handle.read().hex()
                                except Exception as e:
                                    print(f"⚠️ SKIPPING FILE: {rel_path} - {e}")
                                    continue

                print(f"📁 RAW PROJECT: Collected {len(all_project_files)} total files")

                update_analysis_progress(
                    session_id,
                    "Analyzing project structure",
                    90,
                    f"Processing {len(all_project_files)} files with AI...",
                )
                time.sleep(0.5)

                # Use ChatGPT to intelligently identify artifacts to exclude
                artifact_analysis = identify_artifacts_with_gpt(
                    all_project_files, project_type
                )
                excluded_dirs = artifact_analysis["directories"]
                excluded_patterns = artifact_analysis["patterns"]
                exclusion_reasoning = artifact_analysis["reasoning"]

                print("🧠 CHATGPT EXCLUSIONS:")
                print(f"   Directories: {excluded_dirs}")
                print(f"   File patterns: {excluded_patterns}")
                print(f"   Reasoning: {exclusion_reasoning}")

                # Apply ChatGPT's exclusions to filter project files
                project_files = {}
                excluded_files = []
                important_build_files = [
                    "build.sbt",
                    "build.gradle",
                    "build.gradle.kts",
                    "pom.xml",
                    "requirements.txt",
                    "package.json",
                    "Cargo.toml",
                    "pyproject.toml",
                ]

                for file_path, content in all_project_files.items():
                    should_exclude = False

                    # NEVER exclude important build files
                    filename = os.path.basename(file_path)
                    if filename in important_build_files:
                        print(f"✅ PRESERVING BUILD FILE: {file_path}")
                        project_files[file_path] = content
                        continue

                    # Check directory exclusions
                    for excluded_dir in excluded_dirs:
                        if f"/{excluded_dir}/" in file_path.replace(
                            "\\", "/"
                        ) or file_path.replace("\\", "/").startswith(
                            f"{excluded_dir}/"
                        ):
                            should_exclude = True
                            excluded_files.append(
                                f"{file_path} (directory: {excluded_dir})"
                            )
                            break

                    # Check file pattern exclusions
                    if not should_exclude:
                        for pattern in excluded_patterns:
                            if (
                                pattern.startswith("*.")
                                and file_path.endswith(pattern[1:])
                            ) or pattern in file_path:
                                should_exclude = True
                                excluded_files.append(
                                    f"{file_path} (pattern: {pattern})"
                                )
                                break

                    if not should_exclude:
                        project_files[file_path] = content
                    else:
                        print(f"🚫 CHATGPT EXCLUDED: {file_path}")

                print(
                    f"📁 CLEAN PROJECT: {len(project_files)} files after ChatGPT filtering ({len(excluded_files)} excluded)"
                )

                update_analysis_progress(
                    session_id,
                    "Finalizing analysis",
                    95,
                    "Preparing results and update options...",
                )
                time.sleep(0.5)

                # Create temp file with specific naming for easier lookup
                update_session_id = str(
                    int(time.time() * 1000)
                )  # Use different variable name
                temp_data_path = Config.get_temp_data_path(update_session_id)

                # Get user instructions from the analysis session
                user_instructions = analysis_status[session_id].get(
                    "user_instructions", ""
                )

                with open(temp_data_path, "w") as temp_data:
                    json.dump(
                        {
                            "project_type": project_type,
                            "dep_file_name": dep_file_name,
                            "dependencies": [
                                {
                                    "name": d.name,
                                    "current_version": d.current_version,
                                    "latest_version": d.latest_version,
                                    "description": d.description,
                                }
                                for d in dependencies
                            ],
                            "project_files": project_files,
                            "exclusion_analysis": {
                                "excluded_directories": excluded_dirs,
                                "excluded_patterns": excluded_patterns,
                                "reasoning": exclusion_reasoning,
                                "excluded_files": excluded_files,
                                "total_files_before": len(all_project_files),
                                "total_files_after": len(project_files),
                            },
                            "user_instructions": user_instructions,
                        },
                        temp_data,
                    )

                # Generate final results
                update_analysis_progress(
                    session_id,
                    "Analysis complete!",
                    100,
                    f"Found {len(dependencies)} dependencies, {sum(1 for d in dependencies if d.current_version != d.latest_version)} updates available",
                )

                # Store the analysis results for the completion page (convert Dependency objects to dicts)
                analysis_status[session_id]["results"] = {
                    "project_type": project_type,
                    "dependencies": [
                        {
                            "name": d.name,
                            "current_version": d.current_version,
                            "latest_version": d.latest_version,
                            "description": d.description,
                        }
                        for d in dependencies
                    ],
                    "update_session_id": update_session_id,
                }

                # Update project history with completion status
                if "user_id" in analysis_status[session_id]:

                    async def update_history():
                        async with AsyncSessionLocal() as db:
                            user_service = UserService(db)
                            updates_count = sum(
                                1
                                for d in dependencies
                                if d.current_version != d.latest_version
                            )
                            await user_service.update_project_status(
                                session_id=session_id,
                                status="completed",
                                dependencies_count=len(dependencies),
                                updates_count=updates_count,
                                metadata={
                                    "project_type": project_type,
                                    "dep_file_name": dep_file_name,
                                    "update_session_id": update_session_id,
                                },
                            )
                            print(
                                f"📊 HISTORY: Updated project status to completed for session {session_id}"
                            )

                    asyncio.run(update_history())

                print(
                    f"✅ ANALYSIS COMPLETE: Session {session_id} finished successfully"
                )

            except Exception as analysis_err:
                error_msg = f"Error during project analysis: {analysis_err!s}"
                print(f"❌ ANALYSIS ERROR at 85%+: {analysis_err}")
                update_analysis_progress(
                    session_id,
                    "Analysis failed",
                    0,
                    error_msg,
                )

                # Update project history with error
                if "user_id" in analysis_status.get(session_id, {}):

                    async def update_error():
                        async with AsyncSessionLocal() as db:
                            user_service = UserService(db)
                            await user_service.update_project_status(
                                session_id=session_id,
                                status="failed",
                                error_message=error_msg,
                            )

                    asyncio.run(update_error())
                return

    except Exception as outer_err:
        error_message = str(outer_err)
        update_analysis_progress(
            session_id, "Analysis failed", 0, f"Error: {outer_err!s}"
        )
        print(f"ERROR in analysis process: {outer_err}")

        # Update project history with error
        if session_id in analysis_status and "user_id" in analysis_status[session_id]:

            async def update_final_error():
                async with AsyncSessionLocal() as db:
                    user_service = UserService(db)
                    await user_service.update_project_status(
                        session_id=session_id,
                        status="failed",
                        error_message=error_message,
                    )

            asyncio.run(update_final_error())


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
    """Start the analysis process"""
    print(f"🚀 START-ANALYSIS: Request to start analysis for session {session_id}")
    print(f"🚀 START-ANALYSIS: Available sessions: {list(analysis_status.keys())}")

    if session_id not in analysis_status:
        print(f"❌ START-ANALYSIS: Session {session_id} not found!")
        return {"success": False, "error": f"Session {session_id} not found"}

    def run_analysis_process():
        """Run the actual analysis process in a separate thread"""
        print(f"🔄 THREAD: Starting analysis thread for session {session_id}")
        analyze_dependencies_with_progress(session_id)

    # Start the analysis process in a background thread
    thread = threading.Thread(target=run_analysis_process)
    thread.daemon = True
    thread.start()
    print(f"🚀 START-ANALYSIS: Analysis thread started for session {session_id}")

    # Return immediately so SSE can start streaming progress
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
            status = '<span class="status-chip status-update">🔄 Update available</span>'
            status_class = "update-available"
            updates_available += 1
        else:
            status = '<span class="status-chip status-current">✅ Up to date</span>'
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
