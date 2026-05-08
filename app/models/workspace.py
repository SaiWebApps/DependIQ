"""
Workspace model for team/organization-level project grouping
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .project_library import ProjectLibrary
    from .user import User
    from .workspace_member import WorkspaceMember


class Workspace(Base):
    """
    Workspace model

    Represents a team workspace that groups projects and members.
    """

    __tablename__ = "workspaces"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workspace name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Owner (creator) of the workspace
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="workspaces")
    members: Mapped[list["WorkspaceMember"]] = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ProjectLibrary"]] = relationship(
        "ProjectLibrary", back_populates="workspace"
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, name={self.name})>"

    def to_dict(self) -> dict:
        """Convert workspace to dictionary"""
        return {
            "id": str(self.id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
