"""
Relationship detection API routes.

Provides endpoints to trigger cross-project relationship analysis
and retrieve detected relationships for a user's projects.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal, get_db
from ..graph.service import GraphService
from ..middleware import get_current_user
from ..models.job import Job, JobStatus
from ..models.project_library import ProjectLibrary
from ..models.user import User
from ..services.relationship_service import RelationshipService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relationships", tags=["relationships"])


# Pydantic response models


class AnalyzeResponse(BaseModel):
    """Response from triggering relationship analysis."""

    task_id: str
    status: str


class RelationshipResponse(BaseModel):
    """A single detected relationship."""

    source_project_id: str
    source_name: str
    target_project_id: str
    target_name: str
    relationship_type: str
    confidence: float
    evidence: str = ""


class RelationshipListResponse(BaseModel):
    """List of all detected relationships."""

    relationships: list[RelationshipResponse]
    total: int


# Background task runner


async def _run_relationship_detection(user_id: str, job_id: str) -> None:
    """
    Background task that runs relationship detection.

    Creates its own DB session since it runs outside the request lifecycle.
    """
    async with AsyncSessionLocal() as db:
        try:
            graph_service = GraphService()
            service = RelationshipService(db=db, graph_service=graph_service)
            await service.detect_relationships(user_id=user_id, job_id=job_id)
        except Exception as e:
            logger.error("Relationship detection failed for user %s: %s", user_id, e)
            # Mark job as failed
            job_uuid = uuid.UUID(job_id)
            result = await db.execute(select(Job).where(Job.id == job_uuid))
            job = result.scalar_one_or_none()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                await db.commit()


# Routes


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_relationships(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """
    Trigger cross-project relationship analysis for all user projects.

    Creates a background job that:
    1. Finds shared dependencies between projects (instant)
    2. Uses LLM to detect deeper relationships (imports, API calls, shared DBs)
    3. Writes results to the graph service

    Returns a task_id to track progress.
    """
    # Verify user has at least 2 projects
    result = await db.execute(
        select(ProjectLibrary).where(ProjectLibrary.user_id == current_user.id)
    )
    projects = result.scalars().all()

    if len(projects) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Need at least 2 projects to analyze relationships",
        )

    # Create tracking job
    job = Job(
        user_id=current_user.id,
        job_type="relationship_detection",
        status=JobStatus.QUEUED.value,
        job_name="Cross-project relationship detection",
        job_description=f"Analyzing relationships between {len(projects)} projects",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    background_tasks.add_task(
        _run_relationship_detection,
        user_id=str(current_user.id),
        job_id=str(job.id),
    )

    return AnalyzeResponse(task_id=str(job.id), status="pending")


@router.get("/", response_model=RelationshipListResponse)
async def list_relationships(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RelationshipListResponse:
    """
    List all detected relationships between the user's projects.

    Returns relationships from the graph service, enriched with project names.
    """
    # Get all user project IDs for filtering
    result = await db.execute(
        select(ProjectLibrary).where(ProjectLibrary.user_id == current_user.id)
    )
    projects = {str(p.id): p.project_name for p in result.scalars().all()}

    if not projects:
        return RelationshipListResponse(relationships=[], total=0)

    # Get relationships from graph service
    graph_service = GraphService()
    all_rels = await graph_service.get_relationships()

    # Filter to only relationships between this user's projects
    user_project_ids = set(projects.keys())
    user_rels: list[RelationshipResponse] = []

    for rel in all_rels:
        if (
            rel.source_project_id in user_project_ids
            and rel.target_project_id in user_project_ids
        ):
            user_rels.append(
                RelationshipResponse(
                    source_project_id=rel.source_project_id,
                    source_name=projects.get(rel.source_project_id, "Unknown"),
                    target_project_id=rel.target_project_id,
                    target_name=projects.get(rel.target_project_id, "Unknown"),
                    relationship_type=rel.relationship_type,
                    confidence=rel.confidence,
                    evidence=rel.metadata.get("evidence", ""),
                )
            )

    return RelationshipListResponse(relationships=user_rels, total=len(user_rels))


@router.get("/status/{task_id}")
async def get_analysis_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the status of a relationship analysis job."""
    try:
        job_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID",
        )

    result = await db.execute(
        select(Job).where(Job.id == job_uuid, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return {
        "task_id": str(job.id),
        "status": job.status,
        "progress": job.progress_percentage,
        "current_step": job.current_step,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
