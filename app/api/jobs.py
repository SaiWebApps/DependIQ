"""
Job History API routes
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware import get_current_user
from ..models import Job, JobStatus, User

router = APIRouter(prefix="/jobs", tags=["jobs"])


# Response Models
class JobResponse(BaseModel):
    """Job response"""

    id: str
    job_type: str
    status: str
    job_name: str
    job_description: str | None
    custom_instructions: str | None
    progress_percentage: int
    current_step: str | None
    result_summary: str | None
    pull_request_url: str | None
    error_message: str | None
    project_id: str | None
    project_name: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


# Routes


@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all jobs for the current user

    Optionally filter by status: queued, running, completed, failed, cancelled
    """
    query = select(Job).where(Job.user_id == current_user.id)

    if status_filter:
        query = query.where(Job.status == status_filter)

    query = query.order_by(Job.created_at.desc())

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Build response with project names
    job_responses = []
    for job in jobs:
        project_name = None
        if job.project_id:
            from ..models import ProjectLibrary

            project_result = await db.execute(
                select(ProjectLibrary).where(ProjectLibrary.id == job.project_id)
            )
            project = project_result.scalar_one_or_none()
            if project:
                project_name = project.project_name

        job_responses.append(
            JobResponse(
                id=str(job.id),
                job_type=job.job_type,
                status=job.status,
                job_name=job.job_name,
                job_description=job.job_description,
                custom_instructions=job.custom_instructions,
                progress_percentage=job.progress_percentage,
                current_step=job.current_step,
                result_summary=job.result_summary,
                pull_request_url=job.pull_request_url,
                error_message=job.error_message,
                project_id=str(job.project_id) if job.project_id else None,
                project_name=project_name,
                created_at=job.created_at.isoformat() if job.created_at else "",
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                updated_at=job.updated_at.isoformat() if job.updated_at else "",
            )
        )

    return job_responses


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get details for a specific job
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID"
        )

    result = await db.execute(
        select(Job).where(Job.id == job_uuid, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    # Get project name if job has a project
    project_name = None
    if job.project_id:
        from ..models import ProjectLibrary

        project_result = await db.execute(
            select(ProjectLibrary).where(ProjectLibrary.id == job.project_id)
        )
        project = project_result.scalar_one_or_none()
        if project:
            project_name = project.project_name

    return JobResponse(
        id=str(job.id),
        job_type=job.job_type,
        status=job.status,
        job_name=job.job_name,
        job_description=job.job_description,
        custom_instructions=job.custom_instructions,
        progress_percentage=job.progress_percentage,
        current_step=job.current_step,
        result_summary=job.result_summary,
        pull_request_url=job.pull_request_url,
        error_message=job.error_message,
        project_id=str(job.project_id) if job.project_id else None,
        project_name=project_name,
        created_at=job.created_at.isoformat() if job.created_at else "",
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )


@router.post("/{job_id}/cancel", response_model=MessageResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a running or queued job
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID"
        )

    result = await db.execute(
        select(Job).where(Job.id == job_uuid, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    # Only allow cancellation of queued or running jobs
    if job.status not in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}",
        )

    job.status = JobStatus.CANCELLED.value
    job.updated_at = datetime.utcnow()

    await db.commit()

    return MessageResponse(message="Job cancelled successfully")


@router.delete("/{job_id}", response_model=MessageResponse)
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a job from history
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID"
        )

    result = await db.execute(
        select(Job).where(Job.id == job_uuid, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    await db.delete(job)
    await db.commit()

    return MessageResponse(message="Job deleted successfully")


@router.get("/stats/summary", response_model=dict)
async def get_job_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get summary statistics for user's jobs
    """
    # Get all jobs for user
    result = await db.execute(select(Job).where(Job.user_id == current_user.id))
    jobs = result.scalars().all()

    total = len(jobs)
    queued = sum(1 for j in jobs if j.status == JobStatus.QUEUED.value)
    running = sum(1 for j in jobs if j.status == JobStatus.RUNNING.value)
    completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED.value)
    failed = sum(1 for j in jobs if j.status == JobStatus.FAILED.value)
    cancelled = sum(1 for j in jobs if j.status == JobStatus.CANCELLED.value)

    return {
        "total": total,
        "queued": queued,
        "running": running,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
    }
