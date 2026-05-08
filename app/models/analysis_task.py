"""
AnalysisTask model for tracking background analysis jobs.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .project_library import ProjectLibrary


class AnalysisTask(Base):
    """
    Tracks background analysis tasks for projects.

    Created when a user triggers analysis on a GitHub repo or zip upload.
    Updated as the pipeline progresses through phases.
    """

    __tablename__ = "analysis_tasks"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key to project
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_library.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, running, completed, failed

    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    current_phase: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Results
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    project: Mapped["ProjectLibrary"] = relationship("ProjectLibrary")

    def __repr__(self) -> str:
        return f"<AnalysisTask(id={self.id}, status={self.status}, progress={self.progress_pct}%)>"

    def to_dict(self) -> dict:
        """Convert task to dictionary."""
        return {
            "id": str(self.id),
            "project_id": str(self.project_id),
            "status": self.status,
            "progress_pct": self.progress_pct,
            "current_phase": self.current_phase,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
