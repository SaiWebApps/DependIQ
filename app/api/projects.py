"""
Project Library API routes
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database import get_db
from ..middleware import get_current_user
from ..models import Job, JobStatus, JobType, OAuthConnection, ProjectLibrary, User
from ..services.github_oauth_service import get_github_repositories

router = APIRouter(prefix="/projects", tags=["projects"])


# Request/Response Models
class ProjectSummaryRequest(BaseModel):
    """Request to generate project summary"""

    project_id: str


class ProjectResponse(BaseModel):
    """Project response"""

    id: str
    project_name: str
    project_synopsis: str | None
    source_type: str
    github_repo_url: str | None
    github_owner: str | None
    github_repo_name: str | None
    project_type: str | None
    has_updatable_dependencies: bool | None
    dependencies_count: int
    outdated_dependencies_count: int
    created_at: str
    updated_at: str
    last_analyzed_at: str | None


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str
    project_id: str | None = None


# Routes


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    List all projects for the current user
    """
    result = await db.execute(
        select(ProjectLibrary)
        .where(ProjectLibrary.user_id == current_user.id)
        .order_by(ProjectLibrary.updated_at.desc())
    )
    projects = result.scalars().all()

    return [
        ProjectResponse(
            id=str(p.id),
            project_name=p.project_name,
            project_synopsis=p.project_synopsis,
            source_type=p.source_type,
            github_repo_url=p.github_repo_url,
            github_owner=p.github_owner,
            github_repo_name=p.github_repo_name,
            project_type=p.project_type,
            has_updatable_dependencies=p.has_updatable_dependencies,
            dependencies_count=p.dependencies_count,
            outdated_dependencies_count=p.outdated_dependencies_count,
            created_at=p.created_at.isoformat() if p.created_at else "",
            updated_at=p.updated_at.isoformat() if p.updated_at else "",
            last_analyzed_at=p.last_analyzed_at.isoformat()
            if p.last_analyzed_at
            else None,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get details for a specific project
    """
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID"
        )

    result = await db.execute(
        select(ProjectLibrary).where(
            ProjectLibrary.id == project_uuid, ProjectLibrary.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return ProjectResponse(
        id=str(project.id),
        project_name=project.project_name,
        project_synopsis=project.project_synopsis,
        source_type=project.source_type,
        github_repo_url=project.github_repo_url,
        github_owner=project.github_owner,
        github_repo_name=project.github_repo_name,
        project_type=project.project_type,
        has_updatable_dependencies=project.has_updatable_dependencies,
        dependencies_count=project.dependencies_count,
        outdated_dependencies_count=project.outdated_dependencies_count,
        created_at=project.created_at.isoformat() if project.created_at else "",
        updated_at=project.updated_at.isoformat() if project.updated_at else "",
        last_analyzed_at=(
            project.last_analyzed_at.isoformat() if project.last_analyzed_at else None
        ),
    )


@router.post("/upload", response_model=MessageResponse)
async def upload_project(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a project zip file
    """
    # Validate file type
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip files are supported",
        )

    # Generate unique filename
    project_id = uuid.uuid4()
    upload_dir = os.path.join(Config.TEMP_DIR, "uploads", str(current_user.id))
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, f"{project_id}.zip")

    # Save file
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e!s}",
        )

    # Create project record
    project = ProjectLibrary(
        id=project_id,
        user_id=current_user.id,
        project_name=file.filename.replace(".zip", ""),
        source_type="zip_upload",
        zip_file_path=file_path,
        original_filename=file.filename,
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return MessageResponse(
        message="Project uploaded successfully",
        project_id=str(project.id),
    )


@router.get("/github/repositories", response_model=list[dict])
async def get_github_repos(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get GitHub repositories for the current user
    Requires GitHub OAuth connection
    """
    # Check if user has GitHub connection
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.user_id == current_user.id,
            OAuthConnection.provider == "github",
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected. Please connect your GitHub account first.",
        )

    # Get repositories
    repos = await get_github_repositories(connection.access_token)

    if repos is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch GitHub repositories",
        )

    return repos


@router.post("/github/import/{owner}/{repo}", response_model=MessageResponse)
async def import_github_repo(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a GitHub repository as a project
    """
    # Check if user has GitHub connection
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.user_id == current_user.id,
            OAuthConnection.provider == "github",
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected",
        )

    # Check if project already exists
    github_url = f"https://github.com/{owner}/{repo}"
    existing_result = await db.execute(
        select(ProjectLibrary).where(
            ProjectLibrary.user_id == current_user.id,
            ProjectLibrary.github_repo_url == github_url,
        )
    )
    existing_project = existing_result.scalar_one_or_none()

    if existing_project:
        return MessageResponse(
            message="Project already exists in your library",
            project_id=str(existing_project.id),
        )

    # Create project record
    project = ProjectLibrary(
        user_id=current_user.id,
        project_name=repo,
        source_type="github",
        github_repo_url=github_url,
        github_owner=owner,
        github_repo_name=repo,
        github_default_branch="main",  # Default, can be updated
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return MessageResponse(
        message="GitHub repository imported successfully",
        project_id=str(project.id),
    )


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a project from the library
    """
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID"
        )

    result = await db.execute(
        select(ProjectLibrary).where(
            ProjectLibrary.id == project_uuid, ProjectLibrary.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Delete associated zip file if it exists
    if project.zip_file_path and os.path.exists(project.zip_file_path):
        try:
            os.remove(project.zip_file_path)
        except Exception as e:
            print(f"Warning: Failed to delete file {project.zip_file_path}: {e}")

    await db.delete(project)
    await db.commit()

    return MessageResponse(message="Project deleted successfully")


@router.post("/{project_id}/generate-docs", response_model=dict)
async def generate_documentation(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate documentation for a project (creates a job)
    """
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID"
        )

    result = await db.execute(
        select(ProjectLibrary).where(
            ProjectLibrary.id == project_uuid, ProjectLibrary.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Create documentation generation job
    job = Job(
        user_id=current_user.id,
        project_id=project.id,
        job_type=JobType.DOCUMENTATION_GENERATION.value,
        status=JobStatus.QUEUED.value,
        job_name=f"Generate documentation for {project.project_name}",
        job_description="AI-generated documentation with pull request",
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "message": "Documentation generation job created",
        "job_id": str(job.id),
        "status": job.status,
    }


@router.post("/{project_id}/update-dependencies", response_model=dict)
async def update_dependencies(
    project_id: str,
    custom_instructions: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update dependencies for a project (creates a job)
    """
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project ID"
        )

    result = await db.execute(
        select(ProjectLibrary).where(
            ProjectLibrary.id == project_uuid, ProjectLibrary.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Create dependency update job
    job = Job(
        user_id=current_user.id,
        project_id=project.id,
        job_type=JobType.DEPENDENCY_UPDATE.value,
        status=JobStatus.QUEUED.value,
        job_name=f"Update dependencies for {project.project_name}",
        job_description="Update project dependencies to latest versions",
        custom_instructions=custom_instructions,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "message": "Dependency update job created",
        "job_id": str(job.id),
        "status": job.status,
    }
