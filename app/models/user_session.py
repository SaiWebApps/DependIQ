"""
User session model for server-side session storage (GitHub operations)
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class UserSession(Base):
    """
    User session model

    Stores server-side sessions for GitHub operations (creating PRs, etc.)
    """

    __tablename__ = "user_sessions"

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

    # Session token
    session_token: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # OAuth state for validation
    oauth_state: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # GitHub access token (stored for operations)
    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional session data
    session_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession(id={self.id}, user_id={self.user_id})>"

    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> dict:
        """Convert session to dictionary (excluding sensitive data)"""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
        }
