"""
WorkspaceMember model for workspace membership and roles
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User
    from .workspace import Workspace


class WorkspaceMember(Base):
    """
    WorkspaceMember model

    Tracks which users belong to which workspaces and their role.
    Roles: owner, member, viewer
    """

    __tablename__ = "workspace_members"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign keys
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Role within the workspace
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace", back_populates="members"
    )
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<WorkspaceMember(workspace_id={self.workspace_id}, user_id={self.user_id}, role={self.role})>"

    def to_dict(self) -> dict:
        """Convert workspace member to dictionary"""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "user_id": str(self.user_id),
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }
