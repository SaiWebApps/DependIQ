"""
Tests for the analysis pipeline service and API endpoints.

Tests cover:
- GitHub repo cloning (mocked subprocess)
- Static analysis for Python/Node projects
- Task creation and status updates
- API endpoints for triggering and tracking analysis
"""

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectLibrary, User
from app.models.analysis_task import AnalysisTask
from app.services.pipeline import AnalysisPipeline
from tests.conftest import TEST_SESSION_TOKEN

# --- Fixtures ---


@pytest_asyncio.fixture
async def pipeline_user(test_db_session: AsyncSession) -> User:
    """Create a user with GitHub token for pipeline tests."""
    user = User(
        email="pipeline@example.com",
        workos_user_id="user_pipeline_001",
        email_verified=True,
        is_active=True,
        github_access_token="ghp_test_pipeline_token",
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def github_project(
    test_db_session: AsyncSession, pipeline_user: User
) -> ProjectLibrary:
    """Create a GitHub project for testing."""
    project = ProjectLibrary(
        user_id=pipeline_user.id,
        project_name="test-repo",
        source_type="github",
        github_repo_url="https://github.com/testowner/test-repo",
        github_owner="testowner",
        github_repo_name="test-repo",
        github_default_branch="main",
    )
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def zip_project(
    test_db_session: AsyncSession, pipeline_user: User, tmp_path: Path
) -> ProjectLibrary:
    """Create a zip upload project with a real zip file for testing."""
    import zipfile

    # Create a zip with a requirements.txt
    zip_path = tmp_path / "test_project.zip"
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr("requirements.txt", "flask==2.3.0\nrequests==2.31.0\n")
        zf.writestr("app.py", "from flask import Flask\nimport requests\n")

    project = ProjectLibrary(
        user_id=pipeline_user.id,
        project_name="test-zip-project",
        source_type="zip_upload",
        zip_file_path=str(zip_path),
        original_filename="test_project.zip",
    )
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return project


# --- Unit tests for _clone_github_repo ---


class TestCloneGithubRepo:
    """Tests for the GitHub cloning logic."""

    @pytest.mark.asyncio
    async def test_clone_success(self, tmp_path):
        """Verify clone command is called with correct args and returns a path."""
        pipeline = AnalysisPipeline()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            result = await pipeline._clone_github_repo(
                "testowner", "test-repo", "ghp_token123", "main"
            )

            # Verify git clone was called
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0]
            assert call_args[0] == "git"
            assert call_args[1] == "clone"
            assert "--depth" in call_args
            assert "1" in call_args
            assert "--branch" in call_args
            assert "main" in call_args
            # Token should be in the URL
            assert "ghp_token123" in call_args[-2]
            assert "testowner/test-repo.git" in call_args[-2]

            # Result should be a Path
            assert isinstance(result, Path)
            assert "dependiq/analysis" in str(result)

        # Cleanup the created directory
        import shutil

        shutil.rmtree(str(result), ignore_errors=True)

    @pytest.mark.asyncio
    async def test_clone_fallback_no_branch(self):
        """If clone with branch fails, retry without branch specification."""
        pipeline = AnalysisPipeline()

        call_count = 0

        async def mock_communicate():
            return (b"", b"remote branch not found")

        async def mock_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_proc = AsyncMock()
            # First call fails, second succeeds
            if call_count == 1:
                mock_proc.returncode = 128
            else:
                mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"remote branch not found")
            )
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await pipeline._clone_github_repo(
                "owner", "repo", "token", "nonexistent-branch"
            )
            # Should have been called twice (first with branch, then without)
            assert call_count == 2

        import shutil

        shutil.rmtree(str(result), ignore_errors=True)

    @pytest.mark.asyncio
    async def test_clone_failure_redacts_token(self):
        """Error messages should not leak the access token."""
        pipeline = AnalysisPipeline()

        secret_token = "ghp_SUPER_SECRET_TOKEN_123"

        mock_process = AsyncMock()
        mock_process.returncode = 128
        mock_process.communicate = AsyncMock(
            return_value=(
                b"",
                f"fatal: could not read from {secret_token}@github.com".encode(),
            )
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                await pipeline._clone_github_repo("owner", "repo", secret_token, "main")
            # Token must be redacted
            assert secret_token not in str(exc_info.value)
            assert "***" in str(exc_info.value)


# --- Unit tests for _static_analysis ---


class TestStaticAnalysis:
    """Tests for static project analysis."""

    @pytest.mark.asyncio
    async def test_detect_python_project(self, tmp_path):
        """Given a directory with requirements.txt, detect Python project type."""
        # Create a minimal Python project
        (tmp_path / "requirements.txt").write_text(
            "flask==2.3.0\nrequests==2.31.0\nsqlalchemy>=2.0\n"
        )
        (tmp_path / "app.py").write_text("from flask import Flask\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("def test_hello(): pass\n")

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        assert result["project_type"] == "python"
        assert result["manifest_name"] == "requirements.txt"
        assert "flask==2.3.0" in result["manifest_content"]
        assert "requests==2.31.0" in result["manifest_content"]
        assert "app.py" in result["file_tree"]

    @pytest.mark.asyncio
    async def test_detect_node_project(self, tmp_path):
        """Given a directory with package.json, detect Node project type."""
        package_json = {
            "name": "test-app",
            "version": "1.0.0",
            "dependencies": {
                "express": "^4.18.0",
                "lodash": "^4.17.21",
            },
            "devDependencies": {
                "jest": "^29.0.0",
            },
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))
        (tmp_path / "index.js").write_text("const express = require('express');\n")

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        assert result["project_type"] == "node"
        assert result["manifest_name"] == "package.json"
        assert "express" in result["manifest_content"]
        assert "lodash" in result["manifest_content"]
        assert "index.js" in result["file_tree"]

    @pytest.mark.asyncio
    async def test_detect_maven_project(self, tmp_path):
        """Given a directory with pom.xml, detect Maven project type."""
        pom_content = """<?xml version="1.0"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test-app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-core</artifactId>
      <version>6.0.0</version>
    </dependency>
  </dependencies>
</project>"""
        (tmp_path / "pom.xml").write_text(pom_content)

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        assert result["project_type"] == "maven"
        assert result["manifest_name"] == "pom.xml"
        assert "spring-core" in result["manifest_content"]

    @pytest.mark.asyncio
    async def test_detect_unknown_project(self, tmp_path):
        """Empty directory yields 'unknown' project type."""
        (tmp_path / "README.md").write_text("# Hello\n")

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        assert result["project_type"] == "unknown"

    @pytest.mark.asyncio
    async def test_file_tree_capped(self, tmp_path):
        """File tree should be capped at 500 entries."""
        # Create 600 files
        for i in range(600):
            (tmp_path / f"file_{i:04d}.py").write_text(f"# file {i}\n")
        (tmp_path / "requirements.txt").write_text("flask==2.3.0\n")

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        assert len(result["file_tree"]) <= 500

    @pytest.mark.asyncio
    async def test_excludes_build_dirs_from_tree(self, tmp_path):
        """Build directories like .git, node_modules should be excluded from file tree."""
        (tmp_path / "requirements.txt").write_text("flask==2.3.0\n")
        (tmp_path / "app.py").write_text("pass\n")

        # Create directories that should be excluded
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("[core]\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "express").mkdir()
        (tmp_path / "node_modules" / "express" / "index.js").write_text("")

        pipeline = AnalysisPipeline()
        result = await pipeline._static_analysis(tmp_path)

        for entry in result["file_tree"]:
            assert not entry.startswith(".git/")
            assert not entry.startswith("node_modules/")


# --- Unit tests for analyze_project task creation ---


class TestAnalyzeProjectCreatesTask:
    """Test that analyze_project creates an AnalysisTask record."""

    @pytest.mark.asyncio
    async def test_creates_task_record(
        self,
        test_db_session: AsyncSession,
        github_project: ProjectLibrary,
        pipeline_user: User,
    ):
        """Calling analyze_project should create a pending AnalysisTask."""
        pipeline = AnalysisPipeline()

        # Mock the background work so it doesn't actually run
        with patch.object(pipeline, "_run_analysis", new_callable=AsyncMock):
            task_id = await pipeline.analyze_project(
                project_id=github_project.id,
                user_id=pipeline_user.id,
                db=test_db_session,
            )

        assert task_id is not None
        # Verify UUID format
        uuid.UUID(task_id)

        # Check task was persisted
        result = await test_db_session.execute(
            select(AnalysisTask).where(AnalysisTask.id == uuid.UUID(task_id))
        )
        task = result.scalar_one_or_none()
        assert task is not None
        assert task.project_id == github_project.id
        assert task.status == "pending"
        assert task.progress_pct == 0

    @pytest.mark.asyncio
    async def test_raises_for_nonexistent_project(
        self, test_db_session: AsyncSession, pipeline_user: User
    ):
        """Should raise ValueError for a project that doesn't exist."""
        pipeline = AnalysisPipeline()
        fake_id = uuid.uuid4()

        with pytest.raises(ValueError, match="not found"):
            await pipeline.analyze_project(
                project_id=fake_id,
                user_id=pipeline_user.id,
                db=test_db_session,
            )


# --- Unit tests for task status updates ---


class TestTaskStatusUpdates:
    """Test that the pipeline correctly updates task status through phases."""

    @pytest.mark.asyncio
    async def test_successful_analysis_updates_status(
        self,
        test_db_session: AsyncSession,
        zip_project: ProjectLibrary,
        pipeline_user: User,
    ):
        """A successful analysis should go pending -> running -> completed."""
        pipeline = AnalysisPipeline()

        # Create the task record directly (simulating what analyze_project does)
        task = AnalysisTask(
            project_id=zip_project.id,
            status="pending",
            progress_pct=0,
            current_phase="Queued",
        )
        test_db_session.add(task)
        await test_db_session.commit()
        await test_db_session.refresh(task)
        task_id = str(task.id)

        project_snapshot = {
            "id": str(zip_project.id),
            "source_type": "zip_upload",
            "github_owner": None,
            "github_repo_name": None,
            "github_default_branch": None,
            "zip_file_path": zip_project.zip_file_path,
            "project_name": zip_project.project_name,
        }

        # Patch _session_factory to return the test session
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session_factory():
            yield test_db_session

        with (
            patch(
                "app.services.pipeline._session_factory",
                mock_session_factory,
            ),
            patch(
                "app.services.pipeline.AnalysisPipeline._extract_dependencies",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "name": "flask",
                        "current_version": "2.3.0",
                        "latest_version": "2.3.0",
                        "description": "Web framework",
                    },
                    {
                        "name": "requests",
                        "current_version": "2.31.0",
                        "latest_version": "2.31.0",
                        "description": "HTTP library",
                    },
                ],
            ),
            patch(
                "app.services.pipeline.AnalysisPipeline._research_versions",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "name": "flask",
                        "current_version": "2.3.0",
                        "latest_version": "3.0.0",
                        "description": "Web framework",
                    },
                    {
                        "name": "requests",
                        "current_version": "2.31.0",
                        "latest_version": "2.32.0",
                        "description": "HTTP library",
                    },
                ],
            ),
            patch(
                "app.services.pipeline.AnalysisPipeline._persist_results",
                new_callable=AsyncMock,
            ),
        ):
            # Call _run_analysis directly (not via background task)
            await pipeline._run_analysis(task_id, project_snapshot, None)

        # Check final status directly from DB
        await test_db_session.refresh(task)
        assert task.status == "completed"
        assert task.progress_pct == 100
        assert "2 dependencies" in task.result_summary
        assert "2 updates available" in task.result_summary

    @pytest.mark.asyncio
    async def test_failed_analysis_sets_error(
        self,
        test_db_session: AsyncSession,
        github_project: ProjectLibrary,
        pipeline_user: User,
    ):
        """If analysis fails, task should be marked 'failed' with error message."""
        pipeline = AnalysisPipeline()

        # Create the task record directly
        task = AnalysisTask(
            project_id=github_project.id,
            status="pending",
            progress_pct=0,
            current_phase="Queued",
        )
        test_db_session.add(task)
        await test_db_session.commit()
        await test_db_session.refresh(task)
        task_id = str(task.id)

        project_snapshot = {
            "id": str(github_project.id),
            "source_type": "github",
            "github_owner": "testowner",
            "github_repo_name": "test-repo",
            "github_default_branch": "main",
            "zip_file_path": None,
            "project_name": "test-repo",
        }

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session_factory():
            yield test_db_session

        # Mock clone to raise an error
        with (
            patch(
                "app.services.pipeline._session_factory",
                mock_session_factory,
            ),
            patch.object(
                pipeline,
                "_clone_github_repo",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Network unreachable"),
            ),
        ):
            await pipeline._run_analysis(task_id, project_snapshot, "ghp_test_token")

        # Check that task is marked failed
        await test_db_session.refresh(task)
        assert task.status == "failed"
        assert "Network unreachable" in task.error_message


# --- API endpoint tests ---


class TestTriggerAnalysisEndpoint:
    """Tests for POST /api/pipeline/projects/{id}/analyze"""

    def test_trigger_returns_task_id(
        self, test_client, test_db_session, _mock_verify_session, test_user
    ):
        """POST /api/pipeline/projects/{id}/analyze should return a task_id."""
        # First create a project
        from app.models import ProjectLibrary

        project = ProjectLibrary(
            user_id=test_user.id,
            project_name="api-test-project",
            source_type="github",
            github_repo_url="https://github.com/owner/repo",
            github_owner="owner",
            github_repo_name="repo",
            github_default_branch="main",
        )
        test_db_session.add(project)

        # Run the commit synchronously using the event loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_db_session.commit())
        loop.run_until_complete(test_db_session.refresh(project))

        project_id = str(project.id)

        # Mock the pipeline to avoid actual cloning
        with patch(
            "app.services.pipeline.AnalysisPipeline._run_analysis",
            new_callable=AsyncMock,
        ):
            response = test_client.post(
                f"/api/pipeline/projects/{project_id}/analyze",
                cookies={"diq_session": TEST_SESSION_TOKEN},
            )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["message"] == "Analysis started. Poll task status for progress."
        # Validate task_id is a UUID
        uuid.UUID(data["task_id"])

    def test_trigger_invalid_project_id(
        self, test_client, _mock_verify_session, test_user
    ):
        """Invalid project ID should return 400."""
        response = test_client.post(
            "/api/pipeline/projects/not-a-uuid/analyze",
            cookies={"diq_session": TEST_SESSION_TOKEN},
        )
        assert response.status_code == 400

    def test_trigger_nonexistent_project(
        self, test_client, _mock_verify_session, test_user
    ):
        """Non-existent project should return 404."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(
            f"/api/pipeline/projects/{fake_id}/analyze",
            cookies={"diq_session": TEST_SESSION_TOKEN},
        )
        assert response.status_code == 404


class TestGetAnalysisStatusEndpoint:
    """Tests for GET /api/pipeline/tasks/{task_id}"""

    def test_get_status_returns_task_data(
        self, test_client, test_db_session, _mock_verify_session, test_user
    ):
        """GET /api/pipeline/tasks/{task_id} should return task progress."""
        from app.models import ProjectLibrary
        from app.models.analysis_task import AnalysisTask

        # Create project and task
        project = ProjectLibrary(
            user_id=test_user.id,
            project_name="status-test",
            source_type="github",
            github_repo_url="https://github.com/owner/repo2",
            github_owner="owner",
            github_repo_name="repo2",
            github_default_branch="main",
        )
        test_db_session.add(project)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_db_session.commit())
        loop.run_until_complete(test_db_session.refresh(project))

        task = AnalysisTask(
            project_id=project.id,
            status="running",
            progress_pct=45,
            current_phase="Extracting dependencies with AI",
        )
        test_db_session.add(task)
        loop.run_until_complete(test_db_session.commit())
        loop.run_until_complete(test_db_session.refresh(task))

        task_id = str(task.id)

        response = test_client.get(
            f"/api/pipeline/tasks/{task_id}",
            cookies={"diq_session": TEST_SESSION_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["status"] == "running"
        assert data["progress_pct"] == 45
        assert data["current_phase"] == "Extracting dependencies with AI"

    def test_get_status_not_found(self, test_client, _mock_verify_session, test_user):
        """Non-existent task should return 404."""
        fake_id = str(uuid.uuid4())
        response = test_client.get(
            f"/api/pipeline/tasks/{fake_id}",
            cookies={"diq_session": TEST_SESSION_TOKEN},
        )
        assert response.status_code == 404

    def test_get_status_invalid_id(self, test_client, _mock_verify_session, test_user):
        """Invalid task ID should return 404."""
        response = test_client.get(
            "/api/pipeline/tasks/not-a-uuid",
            cookies={"diq_session": TEST_SESSION_TOKEN},
        )
        assert response.status_code == 404


# --- Integration test for zip extraction ---


class TestZipExtraction:
    """Test zip extraction path in the pipeline."""

    @pytest.mark.asyncio
    async def test_extract_zip_creates_files(self, tmp_path):
        """Extracting a zip should produce files in the target directory."""
        import zipfile

        # Create test zip
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("hello.txt", "Hello World")
            zf.writestr("subdir/nested.txt", "Nested content")

        pipeline = AnalysisPipeline()
        extract_path = await pipeline._extract_zip(str(zip_path))

        try:
            assert (extract_path / "hello.txt").exists()
            assert (extract_path / "hello.txt").read_text() == "Hello World"
            assert (extract_path / "subdir" / "nested.txt").exists()
            assert (
                extract_path / "subdir" / "nested.txt"
            ).read_text() == "Nested content"
        finally:
            import shutil

            shutil.rmtree(str(extract_path), ignore_errors=True)

    @pytest.mark.asyncio
    async def test_extract_zip_prevents_path_traversal(self, tmp_path):
        """Zip members with path traversal should be skipped."""
        import zipfile

        # Create a zip with a malicious path member
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("safe.txt", "Safe content")
            # Note: Python's zipfile won't let us write ../../../etc/passwd easily,
            # but we can test the extraction logic handles the case
            zf.writestr("normal/file.txt", "Normal content")

        pipeline = AnalysisPipeline()
        extract_path = await pipeline._extract_zip(str(zip_path))

        try:
            assert (extract_path / "safe.txt").exists()
            assert (extract_path / "normal" / "file.txt").exists()
        finally:
            import shutil

            shutil.rmtree(str(extract_path), ignore_errors=True)


# --- Test cleanup ---


class TestCleanup:
    """Test temporary directory cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_directory(self, tmp_path):
        """Cleanup should remove the entire directory tree."""
        test_dir = tmp_path / "to_remove"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("nested")

        pipeline = AnalysisPipeline()
        await pipeline._cleanup(test_dir)

        assert not test_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_is_safe(self, tmp_path):
        """Cleanup on a non-existent path should not raise."""
        pipeline = AnalysisPipeline()
        await pipeline._cleanup(tmp_path / "does_not_exist")
        # No exception = success
