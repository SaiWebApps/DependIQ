"""
User preferences model for storing user-specific settings
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class UserPreference(Base):
    """
    User preferences model

    Stores user-specific settings like theme, language, timezone
    """

    __tablename__ = "user_preferences"

    # Primary key (also foreign key to users)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # Preferences
    theme: Mapped[str] = mapped_column(
        String(30), default="light", nullable=False
    )  # 'light', 'dark', 'ocean', 'forest', 'nord', 'dracula', 'system'

    theme_auto_mode: Mapped[str | None] = mapped_column(
        String(20), default=None, nullable=True
    )  # For future use: 'system', 'time', 'circadian'

    language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )  # ISO language codes

    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)

    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Accessibility preferences
    high_contrast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    colorblind_mode: Mapped[str | None] = mapped_column(
        String(20), default=None, nullable=True
    )  # 'protanopia', 'deuteranopia', 'tritanopia', None

    font_size: Mapped[str] = mapped_column(
        String(10), default="normal", nullable=False
    )  # 'normal', 'large', 'xlarge'

    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreference(user_id={self.user_id}, theme={self.theme}, language={self.language})>"

    def to_dict(self) -> dict:
        """Convert preferences to dictionary"""
        return {
            "theme": self.theme,
            "language": self.language,
            "timezone": self.timezone,
            "notifications_enabled": self.notifications_enabled,
            "high_contrast": self.high_contrast,
            "colorblind_mode": self.colorblind_mode,
            "font_size": self.font_size,
            "reduce_motion": self.reduce_motion,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
