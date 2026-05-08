"""
Analysis service: ZIP extraction, project type detection, LLM-driven dependency
analysis, artifact exclusion, and result assembly.

This module contains the business logic extracted from the former
analyze_dependencies_with_progress god-function. The API route
(app/api/analysis.py) dispatches here and handles only HTTP concerns.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import zipfile

from ..config import Config
from ..database import AsyncSessionLocal
from ..models.exclusions import ArtifactExclusionConfig
from ..services.dependency_agent import (
    extract_dependencies_with_gpt,
    identify_artifacts_with_gpt,
    research_latest_versions,
)
from ..services.progress_service import (
    analysis_status,
    update_analysis_progress,
)
from ..services.user_service import UserService
from ..utils.project_utils import collect_sbt_files, detect_project_type

logger = logging.getLogger(__name__)


def run_analysis(session_id: str) -> None:
    """
    Orchestrate the full dependency analysis pipeline for a session.

    Steps:
        1. Validate session and temp file
        2. Extract ZIP and detect project type
        3. Read dependency files (SBT multi-file or single-file)
        4. Call LLM to extract dependencies
        5. Research latest versions via registries
        6. Collect project files and apply artifact exclusions
        7. Persist results and update project history
    """
    try:
        logger.info("ANALYSIS: Starting analysis for session %s", session_id)

        if session_id not in analysis_status:
            update_analysis_progress(session_id, "Error", 0, "Session not found")
            logger.error(
                "ANALYSIS: Session %s not found in analysis_status", session_id
            )
            return

        file_info = analysis_status[session_id]

        if "temp_file_path" not in file_info:
            update_analysis_progress(
                session_id,
                "Error",
                0,
                "Session data incomplete - missing temp_file_path",
            )
            return

        temp_file_path = file_info["temp_file_path"]

        if not os.path.exists(temp_file_path):
            update_analysis_progress(
                session_id, "Error", 0, f"Uploaded file not found: {temp_file_path}"
            )
            return

        # --- Phase 1: Extract ZIP ---
        update_analysis_progress(
            session_id, "Extracting project files", 10, "Reading uploaded ZIP file..."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
                # Zip slip protection: validate each member path stays within tmpdir
                target_dir = os.path.realpath(tmpdir)
                for member in zip_ref.namelist():
                    member_path = os.path.realpath(os.path.join(tmpdir, member))
                    if (
                        not member_path.startswith(target_dir + os.sep)
                        and member_path != target_dir
                    ):
                        logger.warning(
                            "ANALYSIS: Skipping zip member with path traversal: %s",
                            member,
                        )
                        continue
                    zip_ref.extract(member, tmpdir)

            # --- Phase 2: Detect project type ---
            update_analysis_progress(
                session_id,
                "Detecting project type",
                20,
                "Scanning for dependency files...",
            )

            project_type, dep_file_path, dep_file_name = detect_project_type(tmpdir)
            if project_type == "unknown":
                update_analysis_progress(
                    session_id,
                    "Error",
                    0,
                    "Unsupported project type. Supported: requirements.txt, pom.xml, build.gradle, build.sbt",
                )
                return

            # --- Phase 3: Read dependency files ---
            update_analysis_progress(
                session_id, "Reading dependency files", 30, f"Found {dep_file_name}"
            )

            file_content, dep_file_name = _read_dependency_files(
                session_id, project_type, dep_file_path, dep_file_name, tmpdir
            )

            # --- Phase 4: Extract dependencies via LLM ---
            update_analysis_progress(
                session_id,
                "Extracting dependencies with AI",
                45,
                "ChatGPT is parsing your dependency files...",
            )

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

            # --- Phase 5: Research latest versions ---
            update_analysis_progress(
                session_id,
                "Researching latest versions",
                70,
                f"AI is researching latest versions for {len(dependencies)} dependencies...",
            )

            dependencies = research_latest_versions(dependencies, project_type)

            # --- Phase 6: Collect and filter project files ---
            update_analysis_progress(
                session_id,
                "Preparing project analysis",
                85,
                "Collecting project files for intelligent filtering...",
            )

            try:
                all_project_files = _collect_all_project_files(tmpdir)

                update_analysis_progress(
                    session_id,
                    "Analyzing project structure",
                    90,
                    f"Processing {len(all_project_files)} files with AI...",
                )

                artifact_analysis = identify_artifacts_with_gpt(
                    all_project_files, project_type
                )
                excluded_dirs = artifact_analysis["directories"]
                excluded_patterns = artifact_analysis["patterns"]
                exclusion_reasoning = artifact_analysis["reasoning"]

                project_files, excluded_files = _apply_exclusions(
                    all_project_files, excluded_dirs, excluded_patterns
                )

                logger.info(
                    "ANALYSIS: %d files after filtering (%d excluded)",
                    len(project_files),
                    len(excluded_files),
                )

                # --- Phase 7: Persist results ---
                update_analysis_progress(
                    session_id,
                    "Finalizing analysis",
                    95,
                    "Preparing results and update options...",
                )

                update_session_id = str(int(time.time() * 1000))
                user_instructions = analysis_status[session_id].get(
                    "user_instructions", ""
                )

                _persist_analysis_results(
                    session_id=session_id,
                    update_session_id=update_session_id,
                    project_type=project_type,
                    dep_file_name=dep_file_name,
                    dependencies=dependencies,
                    project_files=project_files,
                    excluded_dirs=excluded_dirs,
                    excluded_patterns=excluded_patterns,
                    exclusion_reasoning=exclusion_reasoning,
                    excluded_files=excluded_files,
                    all_project_files=all_project_files,
                    user_instructions=user_instructions,
                )

                # Update project history
                _update_project_history_completed(
                    session_id,
                    project_type,
                    dep_file_name,
                    update_session_id,
                    dependencies,
                )

                logger.info(
                    "ANALYSIS COMPLETE: Session %s finished successfully", session_id
                )

            except Exception as analysis_err:
                error_msg = f"Error during project analysis: {analysis_err!s}"
                logger.error("ANALYSIS ERROR at 85%%+: %s", analysis_err)
                update_analysis_progress(session_id, "Analysis failed", 0, error_msg)
                _update_project_history_failed(session_id, error_msg)
                return

    except Exception as outer_err:
        error_message = str(outer_err)
        update_analysis_progress(
            session_id, "Analysis failed", 0, f"Error: {outer_err!s}"
        )
        logger.error("ERROR in analysis process: %s", outer_err)
        _update_project_history_failed(session_id, error_message)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _read_dependency_files(
    session_id: str,
    project_type: str,
    dep_file_path: str,
    dep_file_name: str,
    tmpdir: str,
) -> tuple[str, str]:
    """Read and return dependency file content. For SBT projects, collects multiple files."""
    if project_type == "sbt":
        update_analysis_progress(
            session_id,
            "Collecting SBT files",
            35,
            "Gathering build.sbt, project/build.properties, and project/plugins.sbt files...",
        )

        sbt_files = collect_sbt_files(tmpdir)
        logger.info(
            "SBT FILES: Collected %d files: %s", len(sbt_files), list(sbt_files.keys())
        )

        combined_content = ""
        for file_path, content in sbt_files.items():
            combined_content += f"\n=== {file_path} ===\n{content}\n"

        return combined_content, f"SBT project files ({len(sbt_files)} files)"

    with open(dep_file_path, encoding="utf-8") as f:
        return f.read(), dep_file_name


def _collect_all_project_files(tmpdir: str) -> dict[str, str]:
    """Walk the extracted project directory and collect all file contents."""
    all_project_files: dict[str, str] = {}

    for root, _, files in os.walk(tmpdir):
        for f in files:
            if f.endswith(".zip"):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, tmpdir)
            try:
                with open(full_path, encoding="utf-8") as file_handle:
                    all_project_files[rel_path] = file_handle.read()
            except (UnicodeDecodeError, ValueError):
                try:
                    with open(full_path, "rb") as file_handle:
                        all_project_files[rel_path] = file_handle.read().hex()
                except Exception as e:
                    logger.warning("SKIPPING FILE: %s - %s", rel_path, e)

    logger.info("RAW PROJECT: Collected %d total files", len(all_project_files))
    return all_project_files


def _apply_exclusions(
    all_project_files: dict[str, str],
    excluded_dirs: list[str],
    excluded_patterns: list[str],
) -> tuple[dict[str, str], list[str]]:
    """
    Filter project files using the LLM-identified exclusion rules,
    delegating to ArtifactExclusionConfig.should_exclude_file for consistency.
    """
    project_files: dict[str, str] = {}
    excluded_files: list[str] = []

    excluded_dirs_set = set(excluded_dirs)
    excluded_patterns_set = set(excluded_patterns)

    for file_path, content in all_project_files.items():
        should_exclude, reason = ArtifactExclusionConfig.should_exclude_file(
            file_path, excluded_dirs_set, excluded_patterns_set
        )
        if should_exclude:
            excluded_files.append(f"{file_path} ({reason})")
        else:
            project_files[file_path] = content

    return project_files, excluded_files


def _persist_analysis_results(
    *,
    session_id: str,
    update_session_id: str,
    project_type: str,
    dep_file_name: str,
    dependencies: list,
    project_files: dict[str, str],
    excluded_dirs: list[str],
    excluded_patterns: list[str],
    exclusion_reasoning: str,
    excluded_files: list[str],
    all_project_files: dict[str, str],
    user_instructions: str,
) -> None:
    """Persist analysis data to temp file and update in-memory session state."""
    temp_data_path = Config.get_temp_data_path(update_session_id)

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

    # Update progress to 100%
    update_analysis_progress(
        session_id,
        "Analysis complete!",
        100,
        f"Found {len(dependencies)} dependencies, "
        f"{sum(1 for d in dependencies if d.current_version != d.latest_version)} updates available",
    )

    # Store results in session for the completion page
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


def _update_project_history_completed(
    session_id: str,
    project_type: str,
    dep_file_name: str,
    update_session_id: str,
    dependencies: list,
) -> None:
    """Update project history DB record to 'completed' status."""
    if "user_id" not in analysis_status.get(session_id, {}):
        return

    async def _do_update():
        async with AsyncSessionLocal() as db:
            user_service = UserService(db)
            updates_count = sum(
                1 for d in dependencies if d.current_version != d.latest_version
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
            logger.info(
                "HISTORY: Updated project status to completed for session %s",
                session_id,
            )

    asyncio.run(_do_update())


def _update_project_history_failed(session_id: str, error_message: str) -> None:
    """Update project history DB record to 'failed' status."""
    if "user_id" not in analysis_status.get(session_id, {}):
        return

    async def _do_update():
        async with AsyncSessionLocal() as db:
            user_service = UserService(db)
            await user_service.update_project_status(
                session_id=session_id,
                status="failed",
                error_message=error_message,
            )

    asyncio.run(_do_update())
