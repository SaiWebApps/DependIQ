"""add extended themes support

Revision ID: f3a4b5c6d7e8
Revises: def7d10c1b07
Create Date: 2025-11-30 06:22:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Extend theme support to include new themes:
    - Ocean Blue
    - Forest Green
    - Nord
    - Dracula
    - System (auto-detection)
    """
    # Extend the theme field from 20 to 30 characters to accommodate new theme names
    op.alter_column(
        "user_preferences",
        "theme",
        existing_type=sa.String(20),
        type_=sa.String(30),
        existing_nullable=False,
    )

    # Add theme_auto_mode field for future auto-switching features
    op.add_column(
        "user_preferences", sa.Column("theme_auto_mode", sa.String(20), nullable=True)
    )


def downgrade() -> None:
    """
    Revert theme support changes
    """
    # Remove theme_auto_mode column
    op.drop_column("user_preferences", "theme_auto_mode")

    # Revert theme field back to 20 characters
    # Note: This will fail if any themes longer than 20 chars exist
    op.alter_column(
        "user_preferences",
        "theme",
        existing_type=sa.String(30),
        type_=sa.String(20),
        existing_nullable=False,
    )
