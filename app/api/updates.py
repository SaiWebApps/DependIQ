"""
Updates API routes for project dependency updates and code fixes
"""

import asyncio
import json
import os
import tempfile
import threading
import time
import zipfile
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..config import Config
from ..database import AsyncSessionLocal
from ..models.dependency import Dependency
from ..services.ai_service import (
    update_dependency_file_with_gpt,
    update_entire_project_with_gpt,
    update_entire_project_with_gpt_with_progress,
)
from ..services.progress_service import update_progress
from ..services.user_service import UserService
from ..utils.file_utils import find_matching_path

router = APIRouter()

# ⚠️ TEMPORARY IN-MEMORY STORAGE - REPLACE WITH DATABASE IN PRODUCTION ⚠️
#
# This in-memory dictionary stores completed project data for download and file viewing.
#
# CRITICAL LIMITATIONS:
# - Data is lost on server restart
# - No persistence across deployments
# - Memory usage grows unbounded without cleanup
# - Not suitable for multi-instance deployments
# - No concurrent access protection
#
# DATA STRUCTURE:
# completed_projects = {
#     "session_id_123456789": {
#         "zip_file": "/tmp/updated_project_123.zip",           # Path to generated ZIP file
#         "updated_files": {                                    # ChatGPT's returned file updates (original paths)
#             "chatgpt_path.py": "updated_content...",
#             "src/main.py": "updated_content..."
#         },
#         "matched_updates": {                                  # Mapped to actual project file paths
#             "actual/project/path.py": "updated_content...",
#             "src/main.py": "updated_content..."
#         },
#         "dependencies": [Dependency(...)],                   # List of dependency objects
#         "project_type": "python"                             # Project type (python, maven, gradle, sbt)
#     }
# }
#
# TODO: Replace with proper database solution:
# - Redis for session storage with TTL
# - PostgreSQL/SQLite for persistent project history
# - Object storage (S3/MinIO) for ZIP files
# - Implement proper cleanup mechanisms
# - Add session expiration and garbage collection
completed_projects: dict[str, dict[str, Any]] = {}


@router.post("/update/")
async def update_project(request: Request):
    """Legacy update endpoint (kept for compatibility)"""
    form = await request.form()
    data_file = form.get("data_file")

    if not data_file or not isinstance(data_file, str) or not os.path.exists(data_file):
        return {"error": "Session expired. Please analyze the project again."}

    # Load stored data
    if isinstance(data_file, str) and os.path.exists(data_file):
        with open(data_file) as f:
            data = json.load(f)
        # Clean up temp data file
        os.unlink(data_file)
    else:
        return {
            "error": "Session expired or invalid file. Please analyze the project again."
        }

    # Recreate dependencies objects
    dependencies = [Dependency(**dep_data) for dep_data in data["dependencies"]]
    project_files = data["project_files"]

    # Create output file
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_output.close()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use ChatGPT to update the entire project
            updated_files = update_entire_project_with_gpt(
                data["project_type"], project_files, dependencies, data["dep_file_name"]
            )

            # Recreate the entire project structure
            for file_path, content in project_files.items():
                full_path = os.path.join(tmpdir, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                # Use updated content if available, otherwise use original
                if file_path in updated_files:
                    file_content = updated_files[file_path]
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(file_content)
                else:
                    # Handle original content (text or binary)
                    if isinstance(content, str):
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                    else:
                        # Binary file stored as hex
                        with open(full_path, "wb") as f:
                            f.write(bytes.fromhex(content))

            # Create ZIP with the entire updated project
            with zipfile.ZipFile(
                temp_output.name, "w", zipfile.ZIP_DEFLATED
            ) as zip_out:
                # Load exclusion analysis to apply consistent filtering
                session_data = data
                exclusion_analysis = session_data.get("exclusion_analysis", {})
                excluded_dirs = exclusion_analysis.get("excluded_directories", [])
                excluded_patterns = exclusion_analysis.get("excluded_patterns", [])
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

                print("🧠 LEGACY ZIP: APPLYING CHATGPT EXCLUSIONS:")
                print(f"   Excluded directories: {excluded_dirs}")
                print(f"   Excluded patterns: {excluded_patterns}")

                for root, dirs, files in os.walk(tmpdir):
                    # Filter out excluded directories during os.walk traversal
                    dirs[:] = [
                        d
                        for d in dirs
                        if not any(d == excluded_dir for excluded_dir in excluded_dirs)
                    ]

                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, tmpdir)

                        # Apply ChatGPT exclusions to each file
                        should_exclude_from_zip = False

                        # NEVER exclude important build files
                        filename = os.path.basename(rel_path)
                        if filename in important_build_files:
                            print(f"✅ LEGACY ZIP: PRESERVING BUILD FILE: {rel_path}")
                        else:
                            # Check directory exclusions
                            for excluded_dir in excluded_dirs:
                                if f"/{excluded_dir}/" in rel_path.replace(
                                    "\\", "/"
                                ) or rel_path.replace("\\", "/").startswith(
                                    f"{excluded_dir}/"
                                ):
                                    should_exclude_from_zip = True
                                    print(
                                        f"🚫 LEGACY ZIP: CHATGPT EXCLUDED (dir {excluded_dir}): {rel_path}"
                                    )
                                    break

                            # Check file pattern exclusions
                            if not should_exclude_from_zip:
                                for pattern in excluded_patterns:
                                    if (
                                        pattern.startswith("*.")
                                        and rel_path.endswith(pattern[1:])
                                    ) or pattern in rel_path:
                                        should_exclude_from_zip = True
                                        print(
                                            f"🚫 LEGACY ZIP: CHATGPT EXCLUDED (pattern {pattern}): {rel_path}"
                                        )
                                        break

                        if not should_exclude_from_zip:
                            zip_out.write(full_path, rel_path)
                            print(f"✅ LEGACY ZIP: Added to ZIP: {rel_path}")

        def cleanup():
            try:
                os.unlink(temp_output.name)
            except:
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
        except:
            pass
        return {"error": f"Update failed: {e!s}"}


@router.post("/start-update/{session_id}")
async def start_update(session_id: str):
    """Start the project update process"""

    def run_update_process():
        """Run the actual update process in a separate thread"""
        try:
            # Load project data
            data_file = Config.get_temp_data_path(session_id)
            if not os.path.exists(data_file):
                update_progress(
                    session_id, "Error: Session expired", 0, "Please start over"
                )
                return

            with open(data_file) as f:
                data = json.load(f)

            update_progress(
                session_id,
                "Initializing update process",
                10,
                "Loading project data and dependencies",
            )
            time.sleep(0.5)  # Allow progress to be seen

            dependencies = [Dependency(**dep_data) for dep_data in data["dependencies"]]
            project_files = data["project_files"]

            # Create output file
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            temp_output.close()

            with tempfile.TemporaryDirectory() as tmpdir:
                # Get user instructions from the session data
                user_instructions = data.get("user_instructions", "")

                # Use ChatGPT to update the entire project
                updated_files = update_entire_project_with_gpt_with_progress(
                    data["project_type"],
                    project_files,
                    dependencies,
                    data["dep_file_name"],
                    session_id,
                    user_instructions,
                )

                print(
                    f"ChatGPT returned updates for {len(updated_files)} files: {list(updated_files.keys())}"
                )

                # FORCE at least one file to be different to test if file writing works
                marker_file = "dependiq_UPDATE_VERIFICATION.txt"

                # Load exclusion analysis from session data
                exclusion_info = ""
                try:
                    with open(data_file) as f:
                        session_data = json.load(f)
                        if "exclusion_analysis" in session_data:
                            analysis = session_data["exclusion_analysis"]
                            exclusion_info = f"""
=== CHATGPT ARTIFACT EXCLUSION ANALYSIS ===
Reasoning: {analysis['reasoning']}
Excluded Directories: {analysis['excluded_directories']}
Excluded File Patterns: {analysis['excluded_patterns']}
Files Before Filtering: {analysis['total_files_before']}
Files After Filtering: {analysis['total_files_after']}
Files Excluded: {len(analysis['excluded_files'])}

Sample Excluded Files:
{chr(10).join(analysis['excluded_files'][:10])}
{'' if len(analysis['excluded_files']) <= 10 else f'... and {len(analysis["excluded_files"]) - 10} more files'}
"""
                except:
                    exclusion_info = "No exclusion analysis available"

                updated_files[
                    marker_file
                ] = f"""dependiq UPDATE VERIFICATION
This file proves the update process is working.
Updated at: {time.time()}
Original project had {len(project_files)} files
ChatGPT suggested {len(updated_files)} file updates
Dependencies with updates: {[d.name for d in dependencies if d.current_version != d.latest_version]}

{exclusion_info}
=== END VERIFICATION ===
"""

                # Also force the dependency file to be updated
                if data["dep_file_name"] not in updated_files:
                    print(
                        f"FORCING update of {data['dep_file_name']} since ChatGPT didn't include it"
                    )
                    dep_content = project_files.get(data["dep_file_name"], "")
                    forced_dep_update = update_dependency_file_with_gpt(
                        data["project_type"],
                        dep_content,
                        dependencies,
                        data["dep_file_name"],
                    )
                    updated_files[data["dep_file_name"]] = forced_dep_update

                update_progress(
                    session_id,
                    "Rebuilding project structure",
                    97,
                    f"Creating updated project files - {len(updated_files)} files to update",
                )
                time.sleep(0.5)

            files_actually_updated = 0

            # First, apply ChatGPT updates to matching original files
            original_paths = list(project_files.keys())
            matched_updates = {}

            for chatgpt_path, updated_content in updated_files.items():
                matching_original_path = find_matching_path(
                    chatgpt_path, original_paths
                )
                if matching_original_path:
                    matched_updates[matching_original_path] = updated_content
                    print(
                        f"MATCHED: ChatGPT '{chatgpt_path}' → Original '{matching_original_path}'"
                    )
                else:
                    # This is a new file that ChatGPT wants to create
                    matched_updates[chatgpt_path] = updated_content
                    print(f"NEW FILE: ChatGPT wants to create '{chatgpt_path}'")

            print(f"MATCHED {len(matched_updates)} file updates from ChatGPT")

            # Use ChatGPT's exclusion analysis from session data (consistent filtering)
            with open(data_file) as f:
                session_data = json.load(f)
            exclusion_analysis = session_data.get("exclusion_analysis", {})
            chatgpt_excluded_dirs = exclusion_analysis.get("excluded_directories", [])
            chatgpt_excluded_patterns = exclusion_analysis.get("excluded_patterns", [])

            # FORCE exclude common build artifacts for SBT projects regardless of ChatGPT analysis
            if data["project_type"] == "sbt":
                mandatory_sbt_exclusions = ["target", ".bloop", ".metals"]
                for mandatory_dir in mandatory_sbt_exclusions:
                    if mandatory_dir not in chatgpt_excluded_dirs:
                        chatgpt_excluded_dirs.append(mandatory_dir)
                        print(f"🔒 FORCE EXCLUDING SBT BUILD DIR: {mandatory_dir}")
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

            print(
                f"🧠 USING CHATGPT EXCLUSIONS: {chatgpt_excluded_dirs} dirs, {chatgpt_excluded_patterns} patterns"
            )

            for file_path, content in project_files.items():
                should_exclude = False

                # NEVER exclude important build files
                filename = os.path.basename(file_path)
                if filename in important_build_files:
                    print(f"✅ PRESERVING BUILD FILE: {file_path}")
                else:
                    # Apply ChatGPT's directory exclusions
                    for excluded_dir in chatgpt_excluded_dirs:
                        if f"/{excluded_dir}/" in file_path.replace(
                            "\\", "/"
                        ) or file_path.replace("\\", "/").startswith(
                            f"{excluded_dir}/"
                        ):
                            should_exclude = True
                            print(
                                f"🚫 CHATGPT EXCLUDED (dir {excluded_dir}): {file_path}"
                            )
                            break

                    # Apply ChatGPT's pattern exclusions
                    if not should_exclude:
                        for pattern in chatgpt_excluded_patterns:
                            if (
                                pattern.startswith("*.")
                                and file_path.endswith(pattern[1:])
                            ) or pattern in file_path:
                                should_exclude = True
                                print(
                                    f"🚫 CHATGPT EXCLUDED (pattern {pattern}): {file_path}"
                                )
                                break

                if should_exclude:
                    continue

                full_path = os.path.join(tmpdir, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                # Use updated content if available, otherwise use original
                if file_path in matched_updates:
                    file_content = matched_updates[file_path]
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    print(f"✅ UPDATED FILE: {file_path}")
                    files_actually_updated += 1
                else:
                    # Handle original content (text or binary)
                    if isinstance(content, str):
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                    else:
                        # Binary file stored as hex
                        with open(full_path, "wb") as f:
                            f.write(bytes.fromhex(content))

            # Create any new files that ChatGPT wanted to add (using same ChatGPT exclusions)
            for chatgpt_path, updated_content in updated_files.items():
                should_exclude = False

                # NEVER exclude important build files
                filename = os.path.basename(chatgpt_path)
                if filename in important_build_files:
                    print(f"✅ PRESERVING NEW BUILD FILE: {chatgpt_path}")
                else:
                    # Apply ChatGPT's directory exclusions
                    for excluded_dir in chatgpt_excluded_dirs:
                        if f"/{excluded_dir}/" in chatgpt_path.replace(
                            "\\", "/"
                        ) or chatgpt_path.replace("\\", "/").startswith(
                            f"{excluded_dir}/"
                        ):
                            should_exclude = True
                            print(
                                f"🚫 CHATGPT EXCLUDED NEW FILE (dir {excluded_dir}): {chatgpt_path}"
                            )
                            break

                    # Apply ChatGPT's pattern exclusions
                    if not should_exclude:
                        for pattern in chatgpt_excluded_patterns:
                            if (
                                pattern.startswith("*.")
                                and chatgpt_path.endswith(pattern[1:])
                            ) or pattern in chatgpt_path:
                                should_exclude = True
                                print(
                                    f"🚫 CHATGPT EXCLUDED NEW FILE (pattern {pattern}): {chatgpt_path}"
                                )
                                break

                if should_exclude:
                    continue

                if chatgpt_path not in [
                    find_matching_path(chatgpt_path, original_paths)
                    for chatgpt_path in updated_files.keys()
                ]:
                    full_path = os.path.join(tmpdir, chatgpt_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    print(f"✅ CREATED NEW FILE: {chatgpt_path}")
                    files_actually_updated += 1

            # Write the verification marker file
            marker_path = os.path.join(tmpdir, marker_file)
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write(updated_files[marker_file])
            print(f"Added verification marker file: {marker_file}")
            files_actually_updated += 1

            print(f"Actually updated {files_actually_updated} files in the project")

            # Create ZIP with the entire updated project
            print(f"📦 CREATING FINAL ZIP: {temp_output.name}")
            with zipfile.ZipFile(
                temp_output.name, "w", zipfile.ZIP_DEFLATED
            ) as zip_out:
                files_added_to_zip = 0

                # APPLY CHATGPT EXCLUSIONS DURING ZIP CREATION TOO!
                # FORCE exclude common build artifacts for SBT projects regardless of ChatGPT analysis
                if data["project_type"] == "sbt":
                    mandatory_sbt_exclusions = ["target", ".bloop", ".metals"]
                    for mandatory_dir in mandatory_sbt_exclusions:
                        if mandatory_dir not in chatgpt_excluded_dirs:
                            chatgpt_excluded_dirs.append(mandatory_dir)
                            print(
                                f"🔒 ZIP: FORCE EXCLUDING SBT BUILD DIR: {mandatory_dir}"
                            )

                print("🧠 APPLYING CHATGPT EXCLUSIONS TO ZIP CREATION:")
                print(f"   Excluded directories: {chatgpt_excluded_dirs}")
                print(f"   Excluded patterns: {chatgpt_excluded_patterns}")

                for root, dirs, files in os.walk(tmpdir):
                    # Filter out excluded directories during os.walk traversal
                    dirs[:] = [
                        d
                        for d in dirs
                        if not any(
                            d == excluded_dir for excluded_dir in chatgpt_excluded_dirs
                        )
                    ]

                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, tmpdir)

                        # Apply ChatGPT exclusions to each file
                        should_exclude_from_zip = False

                        # NEVER exclude important build files
                        filename = os.path.basename(rel_path)
                        if filename in important_build_files:
                            print(f"✅ ZIP: PRESERVING BUILD FILE: {rel_path}")
                        else:
                            # Check directory exclusions
                            for excluded_dir in chatgpt_excluded_dirs:
                                if f"/{excluded_dir}/" in rel_path.replace(
                                    "\\", "/"
                                ) or rel_path.replace("\\", "/").startswith(
                                    f"{excluded_dir}/"
                                ):
                                    should_exclude_from_zip = True
                                    print(
                                        f"🚫 ZIP: CHATGPT EXCLUDED (dir {excluded_dir}): {rel_path}"
                                    )
                                    break

                            # Check file pattern exclusions
                            if not should_exclude_from_zip:
                                for pattern in chatgpt_excluded_patterns:
                                    if (
                                        pattern.startswith("*.")
                                        and rel_path.endswith(pattern[1:])
                                    ) or pattern in rel_path:
                                        should_exclude_from_zip = True
                                        print(
                                            f"🚫 ZIP: CHATGPT EXCLUDED (pattern {pattern}): {rel_path}"
                                        )
                                        break

                        if not should_exclude_from_zip:
                            zip_out.write(full_path, rel_path)
                            print(f"✅ ZIP: Added to ZIP: {rel_path}")
                            files_added_to_zip += 1

                            # Show first few lines if it's a text file we updated
                            if rel_path in matched_updates and any(
                                rel_path.endswith(ext)
                                for ext in [".sbt", ".scala", ".java", ".py"]
                            ):
                                try:
                                    with open(full_path, encoding="utf-8") as f:
                                        first_lines = "".join(f.readlines()[:3])
                                    print(f"    📝 First 3 lines of {rel_path}:")
                                    print(f"    {first_lines.strip()}")
                                except:
                                    pass

                print(
                    f"📦 ZIP COMPLETE: Added {files_added_to_zip} total files to {temp_output.name}"
                )

            # Store the completed project and updated files for viewing
            completed_projects[session_id] = {
                "zip_file": temp_output.name,
                "updated_files": updated_files,  # ChatGPT's returned paths/content
                "matched_updates": matched_updates,  # Actual project paths/content
                "dependencies": dependencies,
                "project_type": data["project_type"],
            }

            # Generate summary table for final progress update (show only actual project files)
            update_summary = []
            # Use matched_updates which contains the actual file paths that were updated
            for file_path, content in matched_updates.items():
                if file_path != marker_file:  # Skip verification file from summary
                    # VALIDATE: Only process actual file paths, not ChatGPT descriptions
                    if not file_path or " " in file_path.replace("/", "").replace(
                        "\\", ""
                    ).replace(".", "").replace("-", "").replace("_", ""):
                        print(
                            f"🚫 SKIPPING INVALID FILE PATH: '{file_path}' (appears to be ChatGPT description)"
                        )
                        continue

                    # Try to extract what changed
                    filename = os.path.basename(file_path)
                    if filename in [
                        "build.sbt",
                        "build.gradle",
                        "build.gradle.kts",
                        "pom.xml",
                        "requirements.txt",
                        "package.json",
                        "pyproject.toml",
                    ]:
                        changes = [
                            d.name + ": " + d.current_version + " → " + d.latest_version
                            for d in dependencies
                            if d.current_version != d.latest_version
                        ]
                        change_summary = (
                            f"Updated {len(changes)} dependencies: "
                            + ", ".join(changes[:3])
                        )
                        if len(changes) > 3:
                            change_summary += f" and {len(changes) - 3} more"
                    else:
                        change_summary = (
                            "Code compatibility updates for new dependency versions"
                        )

                    update_summary.append(
                        f'<tr><td><a href="/view-file/{session_id}/{file_path.replace("/", "%2F")}" target="_blank">{file_path}</a></td><td>{change_summary}</td></tr>'
                    )

            summary_table = f"""
            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                <thead>
                    <tr style="background: #f8f9fa;">
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Updated File</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Changes Made</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(update_summary)}
                </tbody>
            </table>
            """

            # Count actual files shown in summary table (excluding verification marker)
            actual_updated_count = len(
                [f for f in matched_updates.keys() if f != marker_file]
            )

            update_progress(
                session_id,
                "Update completed successfully!",
                100,
                f"Updated {actual_updated_count} files with latest dependencies and compatibility fixes. {summary_table}",
            )

            # Update project history if user_id exists in the original analysis
            from ..services.progress_service import analysis_status

            original_session_id = None
            user_id = None

            # Find the original analysis session that created this update session
            for sid, data in analysis_status.items():
                if data.get("results", {}).get("update_session_id") == session_id:
                    original_session_id = sid
                    user_id = data.get("user_id")
                    break

            if user_id and original_session_id:
                try:

                    async def update_history():
                        async with AsyncSessionLocal() as db:
                            user_service = UserService(db)
                            # Mark the original project as updated
                            if original_session_id:  # Type guard for mypy/pylance
                                await user_service.update_project_status(
                                    session_id=original_session_id,
                                    status="updated",
                                    metadata={
                                        "update_session_id": session_id,
                                        "files_updated": actual_updated_count,
                                        "update_completed_at": time.time(),
                                    },
                                )
                                print(
                                    f"📊 HISTORY: Marked project {original_session_id} as updated"
                                )

                    asyncio.run(update_history())
                except Exception as hist_err:
                    print(f"⚠️ HISTORY: Failed to update history: {hist_err}")

            # Clean up temp data file
            try:
                os.unlink(data_file)
            except:
                pass

        except Exception as update_err:
            error_message = f"Update failed: {update_err!s}"
            update_progress(session_id, "Update failed", 0, f"Error: {update_err!s}")
            print(f"ERROR in update process: {update_err}")

            # Update project history with error
            from ..services.progress_service import analysis_status

            original_session_id = None
            user_id = None

            # Find the original analysis session
            for sid, data in analysis_status.items():
                if data.get("results", {}).get("update_session_id") == session_id:
                    original_session_id = sid
                    user_id = data.get("user_id")
                    break

            if user_id and original_session_id:
                try:

                    async def update_error():
                        async with AsyncSessionLocal() as db:
                            user_service = UserService(db)
                            if original_session_id:  # Type guard for mypy/pylance
                                await user_service.update_project_status(
                                    session_id=original_session_id,
                                    status="failed",
                                    error_message=error_message,
                                )

                    asyncio.run(update_error())
                except Exception as hist_err:
                    print(f"⚠️ HISTORY: Failed to update error history: {hist_err}")

    # Start the update process in a background thread
    thread = threading.Thread(target=run_update_process)
    thread.daemon = True
    thread.start()

    # Return immediately so SSE can start streaming progress
    return {"success": True, "message": "Update started"}
