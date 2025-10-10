"""
Magic link token model for new user registration
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class MagicLinkToken(Base):
    """
    Magic link token for new user registration

    When a new user enters their email, they receive a magic link with:
    1. A secure token
    2. A temporary password

    They use both to complete registration.
    """

    __tablename__ = "magic_link_tokens"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Email for the new user
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Secure token sent in the magic link URL
    token: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # Temporary password sent in the email
    temp_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Token expiration
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Usage tracking
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def is_expired(self) -> bool:
        """Check if token has expired"""
        return datetime.utcnow() > self.expires_at

    def is_used(self) -> bool:
        """Check if token has been used"""
        return self.used_at is not None

    def __repr__(self) -> str:
        return f"<MagicLinkToken(id={self.id}, email={self.email})>"
