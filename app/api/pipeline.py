"""
Pipeline API routes for triggering and tracking project analysis.

Endpoints:
- POST /api/pipeline/projects/{project_id}/analyze — trigger analysis
- GET /api/pipeline/tasks/{task_id} — get task status
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware import get_current_user
from ..models import User
from ..models.analysis_task import AnalysisTask
from ..services.pipeline import get_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# Response models


class AnalyzeResponse(BaseModel):
    """Response when analysis is triggered."""

    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Response for task status queries."""

    id: str
    project_id: str
    status: str
    progress_pct: int
    current_phase: str | None
    result_summary: str | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None


# Routes


@router.post("/projects/{project_id}/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger analysis for a project.

    Creates a background task that clones (for GitHub) or extracts (for zip)
    the project source and runs the full analysis pipeline.
    Returns immediately with a task_id for progress tracking.
    """
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID",
        )

    pipeline = get_pipeline()

    try:
        task_id = await pipeline.analyze_project(
            project_id=project_uuid,
            user_id=current_user.id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return AnalyzeResponse(
        task_id=task_id,
        status="pending",
        message="Analysis started. Poll task status for progress.",
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_analysis_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of an analysis task.

    Uses the injected DB session (supports test DB overrides).
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    result = await db.execute(select(AnalysisTask).where(AnalysisTask.id == task_uuid))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return TaskStatusResponse(**task.to_dict())
