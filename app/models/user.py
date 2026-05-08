"""
User model for authentication and profile management
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .job import Job
    from .project_history import ProjectHistory
    from .project_library import ProjectLibrary
    from .user_preference import UserPreference


class User(Base):
    """
    User account model

    Supports WorkOS AuthKit authentication with provider OAuth tokens.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # WorkOS integration
    workos_user_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # Authentication
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,  # Kept nullable for migration safety; no longer used
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Provider OAuth tokens (stored after WorkOS callback)
    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gitlab_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    bitbucket_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    preferences: Mapped["UserPreference"] = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    project_history: Mapped[list["ProjectHistory"]] = relationship(
        "ProjectHistory", back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ProjectLibrary"]] = relationship(
        "ProjectLibrary", back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

    def to_dict(self) -> dict:
        """Convert user to dictionary (excluding sensitive data)"""
        return {
            "id": str(self.id),
            "email": self.email,
            "email_verified": self.email_verified,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": (
                self.last_login_at.isoformat() if self.last_login_at else None
            ),
        }
