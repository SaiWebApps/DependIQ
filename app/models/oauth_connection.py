"""
OAuth connection model for linked provider accounts
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class OAuthConnection(Base):
    """
    OAuth provider connection model

    Links user accounts to OAuth providers (GitHub, Google, etc.)
    """

    __tablename__ = "oauth_connections"

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

    # Provider information
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'github', 'google', 'microsoft', 'linkedin', 'bitbucket'

    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # OAuth tokens
    access_token: Mapped[str] = mapped_column(Text, nullable=False)

    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional provider data (using JSON for SQLite compatibility)
    provider_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="oauth_connections")

    # Constraints
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_user"),
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )

    def __repr__(self) -> str:
        return f"<OAuthConnection(id={self.id}, provider={self.provider}, user_id={self.user_id})>"

    def to_dict(self) -> dict:
        """Convert OAuth connection to dictionary (excluding sensitive data)"""
        return {
            "id": str(self.id),
            "provider": self.provider,
            "provider_email": self.provider_email,
            "connected_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
