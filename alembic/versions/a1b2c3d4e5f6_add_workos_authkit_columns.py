"""Add WorkOS AuthKit columns to users table

Revision ID: a1b2c3d4e5f6
Revises: def7d10c1b07
Create Date: 2026-05-07 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "def7d10c1b07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add workos_user_id column
    op.add_column(
        "users",
        sa.Column("workos_user_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_users_workos_user_id", "users", ["workos_user_id"], unique=True)

    # Add provider OAuth token columns
    op.add_column(
        "users",
        sa.Column("github_access_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("gitlab_access_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("bitbucket_access_token", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "bitbucket_access_token")
    op.drop_column("users", "gitlab_access_token")
    op.drop_column("users", "github_access_token")
    op.drop_index("ix_users_workos_user_id", table_name="users")
    op.drop_column("users", "workos_user_id")
