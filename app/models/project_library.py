"""
Project Library model for storing user projects
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .job import Job
    from .user import User
    from .workspace import Workspace


class ProjectLibrary(Base):
    """
    Project Library model

    Stores information about user's projects (from GitHub or zip uploads)
    """

    __tablename__ = "project_library"

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

    # Foreign key to workspace (nullable — existing projects may not belong to one)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Project identification
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)

    project_synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source information
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'github' or 'zip_upload'

    # GitHub specific fields
    github_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_default_branch: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # Zip upload specific fields
    zip_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Project metadata
    project_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'python', 'maven', 'gradle', etc.

    has_updatable_dependencies: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )  # None = not analyzed yet

    dependencies_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    outdated_dependencies_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Additional metadata stored as JSON
    dependency_files: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="projects")
    workspace: Mapped["Workspace | None"] = relationship(
        "Workspace", back_populates="projects"
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProjectLibrary(id={self.id}, name={self.project_name}, source={self.source_type})>"

    def to_dict(self) -> dict:
        """Convert project to dictionary"""
        return {
            "id": str(self.id),
            "project_name": self.project_name,
            "project_synopsis": self.project_synopsis,
            "source_type": self.source_type,
            "github_repo_url": self.github_repo_url,
            "github_owner": self.github_owner,
            "github_repo_name": self.github_repo_name,
            "github_default_branch": self.github_default_branch,
            "original_filename": self.original_filename,
            "project_type": self.project_type,
            "has_updatable_dependencies": self.has_updatable_dependencies,
            "dependencies_count": self.dependencies_count,
            "outdated_dependencies_count": self.outdated_dependencies_count,
            "dependency_files": self.dependency_files,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_analyzed_at": self.last_analyzed_at.isoformat()
            if self.last_analyzed_at
            else None,
        }
