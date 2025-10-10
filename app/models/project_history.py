"""
Project history model for tracking user's project uploads and updates
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class ProjectHistory(Base):
    """
    Project history model

    Tracks all project uploads and updates for a user
    """

    __tablename__ = "project_history"

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

    # Session identifier
    session_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )

    # Project information
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'python', 'java', 'scala', etc.

    # Source information
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'zip_upload' or 'github'

    github_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    zip_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default="processing", nullable=False, index=True
    )  # 'processing', 'completed', 'failed'

    dependencies_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    updates_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional data (using JSON for SQLite compatibility)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="project_history")

    def __repr__(self) -> str:
        return f"<ProjectHistory(id={self.id}, session_id={self.session_id}, status={self.status})>"

    def to_dict(self) -> dict:
        """Convert project history to dictionary"""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "project_name": self.project_name,
            "project_type": self.project_type,
            "source_type": self.source_type,
            "github_repo_url": self.github_repo_url,
            "status": self.status,
            "dependencies_count": self.dependencies_count,
            "updates_count": self.updates_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }
