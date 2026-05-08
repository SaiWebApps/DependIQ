"""
Analysis pipeline service: orchestrates project analysis for both
GitHub repos and zip uploads.

Handles:
- Creating AnalysisTask records
- Cloning GitHub repos (shallow, token-authed)
- Static analysis (project type detection, manifest parsing)
- LLM-driven dependency extraction
- Background execution via asyncio.create_task
- Cleanup of temporary files
"""

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models.analysis_task import AnalysisTask
from ..models.project_library import ProjectLibrary
from ..utils.project_utils import collect_sbt_files, detect_project_type

logger = logging.getLogger(__name__)

# Module-level dict for tracking background tasks (simple in-memory tracking)
_running_tasks: dict[str, asyncio.Task] = {}

# Session factory — override in tests to use test database
_session_factory = AsyncSessionLocal


class AnalysisPipeline:
    """Orchestrates project analysis for both GitHub repos and zip uploads."""

    async def analyze_project(
        self, project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
    ) -> str:
        """
        Main entry point. Creates an AnalysisTask and launches background analysis.

        Returns task_id for tracking progress.
        """
        # Verify project exists and belongs to user
        result = await db.execute(
            select(ProjectLibrary).where(
                ProjectLibrary.id == project_id,
                ProjectLibrary.user_id == user_id,
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found for user {user_id}")

        # Look up user's GitHub token if it's a GitHub project
        github_token: str | None = None
        if project.source_type == "github":
            from ..models.user import User

            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                github_token = user.github_access_token

        # Create AnalysisTask record
        task = AnalysisTask(
            project_id=project_id,
            status="pending",
            progress_pct=0,
            current_phase="Queued",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = str(task.id)

        # Snapshot project data for background use (avoid detached session issues)
        project_snapshot = {
            "id": str(project.id),
            "source_type": project.source_type,
            "github_owner": project.github_owner,
            "github_repo_name": project.github_repo_name,
            "github_default_branch": project.github_default_branch,
            "zip_file_path": project.zip_file_path,
            "project_name": project.project_name,
        }

        # Launch background analysis
        bg_task = asyncio.create_task(
            self._run_analysis(task_id, project_snapshot, github_token)
        )
        _running_tasks[task_id] = bg_task

        # Clean up reference when task completes
        bg_task.add_done_callback(lambda t: _running_tasks.pop(task_id, None))

        return task_id

    async def _run_analysis(
        self,
        task_id: str,
        project_snapshot: dict,
        github_token: str | None,
    ) -> None:
        """Background worker. Updates task status as it progresses."""
        clone_path: Path | None = None
        try:
            # Update status to running
            await self._update_task(
                task_id,
                status="running",
                progress_pct=5,
                current_phase="Starting analysis",
                started_at=datetime.utcnow(),
            )

            # Acquire source code
            source_type = project_snapshot["source_type"]
            if source_type == "github":
                owner = project_snapshot["github_owner"]
                repo = project_snapshot["github_repo_name"]
                branch = project_snapshot["github_default_branch"] or "main"

                if not github_token:
                    await self._update_task(
                        task_id,
                        status="failed",
                        progress_pct=0,
                        error_message="GitHub access token not available. Please reconnect your GitHub account.",
                    )
                    return

                await self._update_task(
                    task_id,
                    progress_pct=10,
                    current_phase="Cloning repository",
                )
                clone_path = await self._clone_github_repo(
                    owner, repo, github_token, branch
                )
                project_path = clone_path

            elif source_type == "zip_upload":
                zip_path = project_snapshot["zip_file_path"]
                if not zip_path or not os.path.exists(zip_path):
                    await self._update_task(
                        task_id,
                        status="failed",
                        progress_pct=0,
                        error_message="Upload file not found. Please re-upload the project.",
                    )
                    return

                await self._update_task(
                    task_id,
                    progress_pct=10,
                    current_phase="Extracting zip file",
                )
                clone_path = await self._extract_zip(zip_path)
                project_path = clone_path
            else:
                await self._update_task(
                    task_id,
                    status="failed",
                    progress_pct=0,
                    error_message=f"Unsupported source type: {source_type}",
                )
                return

            # Static analysis
            await self._update_task(
                task_id,
                progress_pct=25,
                current_phase="Detecting project type",
            )
            static_results = await self._static_analysis(project_path)

            if static_results["project_type"] == "unknown":
                await self._update_task(
                    task_id,
                    status="failed",
                    progress_pct=0,
                    error_message="Could not detect project type. Supported: Python, Maven, Gradle, SBT, Node.js",
                )
                return

            # LLM dependency extraction
            await self._update_task(
                task_id,
                progress_pct=45,
                current_phase="Extracting dependencies with AI",
            )
            dependencies = await self._extract_dependencies(
                static_results["project_type"],
                static_results["manifest_content"],
                static_results["manifest_name"],
            )

            if not dependencies:
                await self._update_task(
                    task_id,
                    status="failed",
                    progress_pct=0,
                    error_message=f"Could not extract dependencies from {static_results['manifest_name']}",
                )
                return

            # Research latest versions
            await self._update_task(
                task_id,
                progress_pct=70,
                current_phase="Researching latest versions",
            )
            dependencies = await self._research_versions(
                dependencies, static_results["project_type"]
            )

            # Persist results to project
            await self._update_task(
                task_id,
                progress_pct=90,
                current_phase="Saving results",
            )
            await self._persist_results(
                project_id=uuid.UUID(project_snapshot["id"]),
                project_type=static_results["project_type"],
                dependencies=dependencies,
                file_tree=static_results["file_tree"],
            )

            # Mark complete
            outdated_count = sum(
                1
                for d in dependencies
                if d.get("current_version") != d.get("latest_version")
            )
            summary = (
                f"Found {len(dependencies)} dependencies, "
                f"{outdated_count} updates available. "
                f"Project type: {static_results['project_type']}"
            )
            await self._update_task(
                task_id,
                status="completed",
                progress_pct=100,
                current_phase="Analysis complete",
                result_summary=summary,
                completed_at=datetime.utcnow(),
            )

            logger.info("Analysis complete for task %s", task_id)

        except Exception as e:
            logger.error("Analysis failed for task %s: %s", task_id, e, exc_info=True)
            await self._update_task(
                task_id,
                status="failed",
                progress_pct=0,
                error_message=f"Analysis error: {e!s}",
                completed_at=datetime.utcnow(),
            )
        finally:
            if clone_path:
                await self._cleanup(clone_path)

    async def _clone_github_repo(
        self, owner: str, repo: str, token: str, branch: str = "main"
    ) -> Path:
        """Clone repo to temp directory using shallow clone. Returns path to clone."""
        clone_id = uuid.uuid4().hex
        clone_dir = Path(f"/tmp/dependiq/analysis/{clone_id}")
        clone_dir.mkdir(parents=True, exist_ok=True)

        clone_url = f"https://{token}@github.com/{owner}/{repo}.git"

        process = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            branch,
            clone_url,
            str(clone_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Try without branch specification (default branch might differ)
            shutil.rmtree(clone_dir, ignore_errors=True)
            clone_dir.mkdir(parents=True, exist_ok=True)

            process = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth",
                "1",
                clone_url,
                str(clone_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode(errors="replace")
                # Redact token from error message
                error_msg = error_msg.replace(token, "***")
                raise RuntimeError(f"Git clone failed: {error_msg}")

        logger.info("Cloned %s/%s to %s", owner, repo, clone_dir)
        return clone_dir

    async def _extract_zip(self, zip_path: str) -> Path:
        """Extract zip file to temp directory. Returns path to extracted content."""
        import zipfile

        extract_id = uuid.uuid4().hex
        extract_dir = Path(f"/tmp/dependiq/analysis/{extract_id}")
        extract_dir.mkdir(parents=True, exist_ok=True)

        def _do_extract():
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                target_dir = os.path.realpath(str(extract_dir))
                for member in zip_ref.namelist():
                    member_path = os.path.realpath(
                        os.path.join(str(extract_dir), member)
                    )
                    if (
                        not member_path.startswith(target_dir + os.sep)
                        and member_path != target_dir
                    ):
                        logger.warning(
                            "Skipping zip member with path traversal: %s", member
                        )
                        continue
                    zip_ref.extract(member, str(extract_dir))

        await asyncio.to_thread(_do_extract)
        return extract_dir

    async def _static_analysis(self, project_path: Path) -> dict:
        """
        Parse manifests and detect project type without LLM.

        Returns:
            {
                project_type: str,
                manifest_content: str,
                manifest_name: str,
                file_tree: list[str],
            }
        """
        project_dir = str(project_path)

        # Detect project type
        project_type, dep_file_path, dep_file_name = detect_project_type(project_dir)

        # Build file tree (limited depth)
        file_tree = []
        for root, dirs, files in os.walk(project_dir):
            depth = root[len(project_dir) :].count(os.sep)
            if depth > 4:
                dirs[:] = []
                continue
            dirs[:] = [
                d
                for d in dirs
                if d
                not in {
                    "target",
                    "build",
                    ".gradle",
                    "__pycache__",
                    ".git",
                    "node_modules",
                    ".idea",
                    ".vscode",
                }
            ]
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), project_dir)
                file_tree.append(rel_path)

        # Read manifest content
        manifest_content = ""
        if project_type == "sbt":
            sbt_files = collect_sbt_files(project_dir)
            for file_path, content in sbt_files.items():
                manifest_content += f"\n=== {file_path} ===\n{content}\n"
            dep_file_name = f"SBT project files ({len(sbt_files)} files)"
        elif project_type != "unknown" and dep_file_path:
            try:
                with open(dep_file_path, encoding="utf-8") as f:
                    manifest_content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read manifest %s: %s", dep_file_path, e)

        # Also check for package.json (Node.js) if not already detected
        if project_type == "unknown":
            for root, dirs, files in os.walk(project_dir):
                depth = root[len(project_dir) :].count(os.sep)
                if depth > 3:
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if d != "node_modules"]
                if "package.json" in files:
                    project_type = "node"
                    dep_file_path = os.path.join(root, "package.json")
                    dep_file_name = "package.json"
                    try:
                        with open(dep_file_path, encoding="utf-8") as f:
                            manifest_content = f.read()
                    except (OSError, UnicodeDecodeError):
                        pass
                    break

        return {
            "project_type": project_type,
            "manifest_content": manifest_content,
            "manifest_name": dep_file_name,
            "file_tree": file_tree[:500],  # Cap to avoid memory issues
        }

    async def _extract_dependencies(
        self, project_type: str, file_content: str, file_name: str
    ) -> list[dict]:
        """Extract dependencies using the LLM agent."""
        from ..services.dependency_agent import DependencyAgent

        agent = DependencyAgent()
        deps = await agent.extract_dependencies(project_type, file_content, file_name)
        return [
            {
                "name": d.name,
                "current_version": d.current_version,
                "latest_version": getattr(d, "latest_version", d.current_version),
                "description": d.description,
            }
            for d in deps
        ]

    async def _research_versions(
        self, dependencies: list[dict], project_type: str
    ) -> list[dict]:
        """Research latest versions for extracted dependencies."""
        from ..models.dependency import Dependency
        from ..services.dependency_agent import DependencyAgent

        # Convert dicts to Dependency objects
        dep_objects = [
            Dependency(
                name=d["name"],
                current_version=d["current_version"],
                description=d.get("description", ""),
            )
            for d in dependencies
        ]

        agent = DependencyAgent()
        updated = await agent.research_latest_versions(dep_objects, project_type)

        return [
            {
                "name": d.name,
                "current_version": d.current_version,
                "latest_version": d.latest_version,
                "description": d.description,
            }
            for d in updated
        ]

    async def _persist_results(
        self,
        project_id: uuid.UUID,
        project_type: str,
        dependencies: list[dict],
        file_tree: list[str],
    ) -> None:
        """Persist analysis results to the ProjectLibrary record."""
        async with _session_factory() as db:
            result = await db.execute(
                select(ProjectLibrary).where(ProjectLibrary.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                logger.error("Project %s not found for persisting results", project_id)
                return

            outdated_count = sum(
                1
                for d in dependencies
                if d.get("current_version") != d.get("latest_version")
            )

            project.project_type = project_type
            project.dependencies_count = len(dependencies)
            project.outdated_dependencies_count = outdated_count
            project.has_updatable_dependencies = outdated_count > 0
            project.last_analyzed_at = datetime.utcnow()
            project.dependency_files = {
                "dependencies": dependencies,
                "file_tree": file_tree[:200],
            }

            await db.commit()

    async def _update_task(self, task_id: str, **kwargs) -> None:
        """Update an AnalysisTask record with the given fields."""
        async with _session_factory() as db:
            result = await db.execute(
                select(AnalysisTask).where(AnalysisTask.id == uuid.UUID(task_id))
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.error("AnalysisTask %s not found for update", task_id)
                return

            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            await db.commit()

    async def _cleanup(self, path: Path) -> None:
        """Remove cloned/extracted files."""
        try:
            await asyncio.to_thread(shutil.rmtree, str(path), True)
            logger.info("Cleaned up analysis directory: %s", path)
        except Exception as e:
            logger.warning("Failed to cleanup %s: %s", path, e)


# Module-level singleton
_pipeline: AnalysisPipeline | None = None


def get_pipeline() -> AnalysisPipeline:
    """Get or create the singleton AnalysisPipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = AnalysisPipeline()
    return _pipeline


async def get_task_status(task_id: str) -> dict | None:
    """Fetch the current status of an analysis task."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return None

    async with _session_factory() as db:
        result = await db.execute(
            select(AnalysisTask).where(AnalysisTask.id == task_uuid)
        )
        task = result.scalar_one_or_none()
        if not task:
            return None
        return task.to_dict()
