"""add_magic_link_token_table

Revision ID: def7d10c1b07
Revises:
Create Date: 2025-11-23 16:43:20.300227

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "def7d10c1b07"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create magic_link_tokens table
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("temp_password", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_magic_link_tokens_email"), "magic_link_tokens", ["email"], unique=False
    )
    op.create_index(
        op.f("ix_magic_link_tokens_token"), "magic_link_tokens", ["token"], unique=True
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f("ix_magic_link_tokens_token"), table_name="magic_link_tokens")
    op.drop_index(op.f("ix_magic_link_tokens_email"), table_name="magic_link_tokens")

    # Drop table
    op.drop_table("magic_link_tokens")
