"""
Update service: project rebuild with updated dependencies, file matching,
artifact exclusion, ZIP packaging, and history tracking.

This module contains the business logic extracted from the former
run_update_process god-function. The API route (app/api/updates.py) dispatches
here and handles only HTTP concerns.
"""

import asyncio
import json
import os
import tempfile
import time
import zipfile
from typing import Any

from ..config import Config
from ..database import AsyncSessionLocal
from ..models.dependency import Dependency
from ..models.exclusions import ArtifactExclusionConfig
from ..services.dependency_agent import (
    update_dependency_file_with_gpt,
    update_entire_project_with_gpt_with_progress,
)
from ..services.progress_service import analysis_status, update_progress
from ..services.user_service import UserService
from ..utils.file_utils import find_matching_path

# In-memory storage for completed project data (download and file viewing).
# See updates.py header comment for limitations and future plans.
completed_projects: dict[str, dict[str, Any]] = {}


def run_update(session_id: str) -> None:
    """
    Orchestrate the full project update pipeline for a session.

    Steps:
        1. Load project data from temp file
        2. Call LLM to generate updated files
        3. Match LLM paths to original project paths
        4. Rebuild project directory with exclusion filtering
        5. Package into ZIP
        6. Update project history
    """
    try:
        # --- Phase 1: Load project data ---
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
        time.sleep(0.5)

        dependencies = [Dependency(**dep_data) for dep_data in data["dependencies"]]
        project_files = data["project_files"]

        # Create output file
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        temp_output.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            # --- Phase 2: LLM-driven file updates ---
            user_instructions = data.get("user_instructions", "")

            updated_files = update_entire_project_with_gpt_with_progress(
                data["project_type"],
                project_files,
                dependencies,
                data["dep_file_name"],
                session_id,
                user_instructions,
            )

            print(
                f"ChatGPT returned updates for {len(updated_files)} files: "
                f"{list(updated_files.keys())}"
            )

            # Add verification marker
            marker_file = "dependiq_UPDATE_VERIFICATION.txt"
            exclusion_info = _build_exclusion_info(data_file)
            updated_files[marker_file] = _build_marker_content(
                project_files, updated_files, dependencies, exclusion_info
            )

            # Force dependency file update if LLM missed it
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

            # --- Phase 3: Match paths and compute exclusions ---
            original_paths = list(project_files.keys())
            matched_updates = _match_updated_paths(updated_files, original_paths)

            exclusion_analysis = data.get("exclusion_analysis", {})
            chatgpt_excluded_dirs = list(
                exclusion_analysis.get("excluded_directories", [])
            )
            chatgpt_excluded_patterns = list(
                exclusion_analysis.get("excluded_patterns", [])
            )

            # Force exclude SBT build artifacts
            if data["project_type"] == "sbt":
                for mandatory_dir in ["target", ".bloop", ".metals"]:
                    if mandatory_dir not in chatgpt_excluded_dirs:
                        chatgpt_excluded_dirs.append(mandatory_dir)

            excluded_dirs_set = set(chatgpt_excluded_dirs)
            excluded_patterns_set = set(chatgpt_excluded_patterns)

            # --- Phase 4: Rebuild project directory ---
            files_actually_updated = _rebuild_project_directory(
                tmpdir=tmpdir,
                project_files=project_files,
                matched_updates=matched_updates,
                updated_files=updated_files,
                original_paths=original_paths,
                excluded_dirs_set=excluded_dirs_set,
                excluded_patterns_set=excluded_patterns_set,
                marker_file=marker_file,
            )

            print(f"Actually updated {files_actually_updated} files in the project")

            # --- Phase 5: Package ZIP ---
            _create_output_zip(
                temp_output_path=temp_output.name,
                tmpdir=tmpdir,
                matched_updates=matched_updates,
                excluded_dirs_set=excluded_dirs_set,
                excluded_patterns_set=excluded_patterns_set,
                project_type=data["project_type"],
            )

            # --- Phase 6: Store results and update history ---
            completed_projects[session_id] = {
                "zip_file": temp_output.name,
                "updated_files": updated_files,
                "matched_updates": matched_updates,
                "dependencies": dependencies,
                "project_type": data["project_type"],
            }

            summary_table = _build_summary_table(
                session_id, matched_updates, marker_file, dependencies
            )
            actual_updated_count = len(
                [f for f in matched_updates.keys() if f != marker_file]
            )

            update_progress(
                session_id,
                "Update completed successfully!",
                100,
                f"Updated {actual_updated_count} files with latest dependencies "
                f"and compatibility fixes. {summary_table}",
            )

            _update_project_history_updated(session_id, actual_updated_count)

            # Clean up temp data file
            try:
                os.unlink(data_file)
            except OSError:
                pass

    except Exception as update_err:
        error_message = f"Update failed: {update_err!s}"
        update_progress(session_id, "Update failed", 0, f"Error: {update_err!s}")
        print(f"ERROR in update process: {update_err}")
        _update_project_history_error(session_id, error_message)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _match_updated_paths(
    updated_files: dict[str, str], original_paths: list[str]
) -> dict[str, str]:
    """Match LLM-returned file paths to actual project paths."""
    matched_updates: dict[str, str] = {}

    for chatgpt_path, updated_content in updated_files.items():
        matching_original_path = find_matching_path(chatgpt_path, original_paths)
        if matching_original_path:
            matched_updates[matching_original_path] = updated_content
            print(f"MATCHED: ChatGPT '{chatgpt_path}' -> Original '{matching_original_path}'")
        else:
            matched_updates[chatgpt_path] = updated_content
            print(f"NEW FILE: ChatGPT wants to create '{chatgpt_path}'")

    print(f"MATCHED {len(matched_updates)} file updates from ChatGPT")
    return matched_updates


def _rebuild_project_directory(
    *,
    tmpdir: str,
    project_files: dict[str, str],
    matched_updates: dict[str, str],
    updated_files: dict[str, str],
    original_paths: list[str],
    excluded_dirs_set: set[str],
    excluded_patterns_set: set[str],
    marker_file: str,
) -> int:
    """
    Write project files to tmpdir, applying updates and exclusions.
    Returns the count of files that were actually updated.
    """
    files_actually_updated = 0

    # Write original files (with updates applied where available)
    for file_path, content in project_files.items():
        should_exclude, _reason = ArtifactExclusionConfig.should_exclude_file(
            file_path, excluded_dirs_set, excluded_patterns_set
        )
        if should_exclude:
            continue

        full_path = os.path.join(tmpdir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        if file_path in matched_updates:
            file_content = matched_updates[file_path]
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"UPDATED FILE: {file_path}")
            files_actually_updated += 1
        else:
            if isinstance(content, str):
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                with open(full_path, "wb") as f:
                    f.write(bytes.fromhex(content))

    # Write new files that LLM wants to create
    for chatgpt_path, updated_content in updated_files.items():
        should_exclude, _reason = ArtifactExclusionConfig.should_exclude_file(
            chatgpt_path, excluded_dirs_set, excluded_patterns_set
        )
        if should_exclude:
            continue

        if chatgpt_path not in [
            find_matching_path(cp, original_paths) for cp in updated_files.keys()
        ]:
            full_path = os.path.join(tmpdir, chatgpt_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            print(f"CREATED NEW FILE: {chatgpt_path}")
            files_actually_updated += 1

    # Write the verification marker file
    marker_path = os.path.join(tmpdir, marker_file)
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write(updated_files[marker_file])
    files_actually_updated += 1

    return files_actually_updated


def _create_output_zip(
    *,
    temp_output_path: str,
    tmpdir: str,
    matched_updates: dict[str, str],
    excluded_dirs_set: set[str],
    excluded_patterns_set: set[str],
    project_type: str,
) -> None:
    """Create the final ZIP file, applying exclusion rules."""
    # Force exclude SBT build artifacts at zip time too
    final_excluded_dirs = set(excluded_dirs_set)
    if project_type == "sbt":
        final_excluded_dirs.update(["target", ".bloop", ".metals"])

    with zipfile.ZipFile(temp_output_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        files_added_to_zip = 0

        for root, dirs, files in os.walk(tmpdir):
            dirs[:] = [
                d for d in dirs if d not in final_excluded_dirs
            ]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, tmpdir)

                should_exclude, _reason = ArtifactExclusionConfig.should_exclude_file(
                    rel_path, final_excluded_dirs, excluded_patterns_set
                )
                if should_exclude:
                    continue

                zip_out.write(full_path, rel_path)
                files_added_to_zip += 1

                # Log first few lines of updated source files
                if rel_path in matched_updates and any(
                    rel_path.endswith(ext)
                    for ext in [".sbt", ".scala", ".java", ".py"]
                ):
                    try:
                        with open(full_path, encoding="utf-8") as f:
                            first_lines = "".join(f.readlines()[:3])
                        print(f"    First 3 lines of {rel_path}: {first_lines.strip()}")
                    except (UnicodeDecodeError, OSError):
                        pass

        print(f"ZIP COMPLETE: Added {files_added_to_zip} total files to {temp_output_path}")


def _build_exclusion_info(data_file: str) -> str:
    """Build exclusion info text for the verification marker file."""
    try:
        with open(data_file) as f:
            session_data = json.load(f)
            if "exclusion_analysis" in session_data:
                analysis = session_data["exclusion_analysis"]
                sample_excluded = "\n".join(analysis["excluded_files"][:10])
                overflow = (
                    f'... and {len(analysis["excluded_files"]) - 10} more files'
                    if len(analysis["excluded_files"]) > 10
                    else ""
                )
                return (
                    f"\n=== CHATGPT ARTIFACT EXCLUSION ANALYSIS ===\n"
                    f"Reasoning: {analysis['reasoning']}\n"
                    f"Excluded Directories: {analysis['excluded_directories']}\n"
                    f"Excluded File Patterns: {analysis['excluded_patterns']}\n"
                    f"Files Before Filtering: {analysis['total_files_before']}\n"
                    f"Files After Filtering: {analysis['total_files_after']}\n"
                    f"Files Excluded: {len(analysis['excluded_files'])}\n\n"
                    f"Sample Excluded Files:\n{sample_excluded}\n{overflow}\n"
                )
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return "No exclusion analysis available"


def _build_marker_content(
    project_files: dict[str, str],
    updated_files: dict[str, str],
    dependencies: list,
    exclusion_info: str,
) -> str:
    """Build the content for the verification marker file."""
    deps_with_updates = [
        d.name for d in dependencies if d.current_version != d.latest_version
    ]
    return (
        f"dependiq UPDATE VERIFICATION\n"
        f"This file proves the update process is working.\n"
        f"Updated at: {time.time()}\n"
        f"Original project had {len(project_files)} files\n"
        f"ChatGPT suggested {len(updated_files)} file updates\n"
        f"Dependencies with updates: {deps_with_updates}\n\n"
        f"{exclusion_info}\n"
        f"=== END VERIFICATION ===\n"
    )


def _build_summary_table(
    session_id: str,
    matched_updates: dict[str, str],
    marker_file: str,
    dependencies: list,
) -> str:
    """Build the HTML summary table for the progress update."""
    update_summary = []
    for file_path in matched_updates:
        if file_path == marker_file:
            continue

        # Skip invalid file paths (LLM descriptions rather than paths)
        clean_name = (
            file_path.replace("/", "").replace("\\", "").replace(".", "")
            .replace("-", "").replace("_", "")
        )
        if not file_path or " " in clean_name:
            print(f"SKIPPING INVALID FILE PATH: '{file_path}'")
            continue

        filename = os.path.basename(file_path)
        if filename in ArtifactExclusionConfig.IMPORTANT_BUILD_FILES:
            changes = [
                d.name + ": " + d.current_version + " -> " + d.latest_version
                for d in dependencies
                if d.current_version != d.latest_version
            ]
            change_summary = (
                f"Updated {len(changes)} dependencies: " + ", ".join(changes[:3])
            )
            if len(changes) > 3:
                change_summary += f" and {len(changes) - 3} more"
        else:
            change_summary = "Code compatibility updates for new dependency versions"

        encoded_path = file_path.replace("/", "%2F")
        update_summary.append(
            f'<tr><td><a href="/view-file/{session_id}/{encoded_path}" '
            f'target="_blank">{file_path}</a></td>'
            f"<td>{change_summary}</td></tr>"
        )

    return f"""
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


def _update_project_history_updated(session_id: str, actual_updated_count: int) -> None:
    """Update project history to 'updated' status."""
    original_session_id, user_id = _find_original_session(session_id)
    if not user_id or not original_session_id:
        return

    try:

        async def _do_update():
            async with AsyncSessionLocal() as db:
                user_service = UserService(db)
                await user_service.update_project_status(
                    session_id=original_session_id,
                    status="updated",
                    metadata={
                        "update_session_id": session_id,
                        "files_updated": actual_updated_count,
                        "update_completed_at": time.time(),
                    },
                )
                print(f"HISTORY: Marked project {original_session_id} as updated")

        asyncio.run(_do_update())
    except Exception as hist_err:
        print(f"HISTORY: Failed to update history: {hist_err}")


def _update_project_history_error(session_id: str, error_message: str) -> None:
    """Update project history to 'failed' status."""
    original_session_id, user_id = _find_original_session(session_id)
    if not user_id or not original_session_id:
        return

    try:

        async def _do_update():
            async with AsyncSessionLocal() as db:
                user_service = UserService(db)
                await user_service.update_project_status(
                    session_id=original_session_id,
                    status="failed",
                    error_message=error_message,
                )

        asyncio.run(_do_update())
    except Exception as hist_err:
        print(f"HISTORY: Failed to update error history: {hist_err}")


def _find_original_session(update_session_id: str) -> tuple[str | None, str | None]:
    """Find the original analysis session that created this update session."""
    for sid, data in analysis_status.items():
        if data.get("results", {}).get("update_session_id") == update_session_id:
            return sid, data.get("user_id")
    return None, None
