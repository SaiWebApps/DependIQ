"""
Job model for tracking dependency update jobs
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .project_library import ProjectLibrary
    from .user import User


class JobStatus(Enum):
    """Job execution status"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Job type"""

    DEPENDENCY_UPDATE = "dependency_update"
    DOCUMENTATION_GENERATION = "documentation_generation"
    DEPENDENCY_ANALYSIS = "dependency_analysis"


class Job(Base):
    """
    Job model

    Tracks all jobs (dependency updates, documentation generation, etc.)
    """

    __tablename__ = "jobs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key to user
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Foreign key to project (optional, for jobs not tied to a specific project)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_library.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Job information
    job_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'dependency_update', 'documentation_generation', etc.

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, default=JobStatus.QUEUED.value
    )

    # Job details
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)

    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Progress tracking
    progress_percentage: Mapped[int] = mapped_column(nullable=False, default=0)  # 0-100

    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Results
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    pull_request_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Session/execution tracking
    session_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )

    # Additional data stored as JSON
    job_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    job_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    project: Mapped["ProjectLibrary"] = relationship(
        "ProjectLibrary", back_populates="jobs"
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, type={self.job_type}, status={self.status})>"

    def to_dict(self) -> dict:
        """Convert job to dictionary"""
        return {
            "id": str(self.id),
            "job_type": self.job_type,
            "status": self.status,
            "job_name": self.job_name,
            "job_description": self.job_description,
            "custom_instructions": self.custom_instructions,
            "progress_percentage": self.progress_percentage,
            "current_step": self.current_step,
            "result_summary": self.result_summary,
            "pull_request_url": self.pull_request_url,
            "error_message": self.error_message,
            "session_id": self.session_id,
            "project_id": str(self.project_id) if self.project_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
