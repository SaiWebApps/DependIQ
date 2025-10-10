"""add accessibility preferences

Revision ID: g4h5i6j7k8l9
Revises: f3a4b5c6d7e8
Create Date: 2025-11-30 18:08:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g4h5i6j7k8l9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add accessibility preference fields:
    - high_contrast: Boolean for high contrast mode
    - colorblind_mode: String for colorblind mode type
    - font_size: String for font size preference
    - reduce_motion: Boolean to reduce animations
    """
    # Add high contrast mode
    op.add_column(
        "user_preferences",
        sa.Column(
            "high_contrast", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # Add colorblind mode
    op.add_column(
        "user_preferences", sa.Column("colorblind_mode", sa.String(20), nullable=True)
    )

    # Add font size preference
    op.add_column(
        "user_preferences",
        sa.Column("font_size", sa.String(10), nullable=False, server_default="normal"),
    )

    # Add reduce motion preference
    op.add_column(
        "user_preferences",
        sa.Column(
            "reduce_motion", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    """
    Remove accessibility preference fields
    """
    op.drop_column("user_preferences", "reduce_motion")
    op.drop_column("user_preferences", "font_size")
    op.drop_column("user_preferences", "colorblind_mode")
    op.drop_column("user_preferences", "high_contrast")
