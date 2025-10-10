"""create project library and jobs tables

Revision ID: a1b2c3d4e5f6
Revises: def7d10c1b07
Create Date: 2025-11-28 10:36:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "84941d6557c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create project_library table
    op.create_table(
        "project_library",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("project_synopsis", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("github_repo_url", sa.String(length=500), nullable=True),
        sa.Column("github_owner", sa.String(length=255), nullable=True),
        sa.Column("github_repo_name", sa.String(length=255), nullable=True),
        sa.Column("github_default_branch", sa.String(length=100), nullable=True),
        sa.Column("zip_file_path", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("project_type", sa.String(length=50), nullable=True),
        sa.Column("has_updatable_dependencies", sa.Boolean(), nullable=True),
        sa.Column(
            "dependencies_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "outdated_dependencies_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("dependency_files", sa.JSON(), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("last_analyzed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_library_user_id"), "project_library", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_library_created_at"),
        "project_library",
        ["created_at"],
        unique=False,
    )

    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="queued"
        ),
        sa.Column("job_name", sa.String(length=255), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column(
            "progress_percentage", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("current_step", sa.String(length=255), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("pull_request_url", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(length=50), nullable=True),
        sa.Column("job_config", sa.JSON(), nullable=True),
        sa.Column("job_results", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project_library.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_jobs_project_id"), "jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_session_id"), "jobs", ["session_id"], unique=False)
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)


def downgrade() -> None:
    # Drop jobs table
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_session_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_project_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_table("jobs")

    # Drop project_library table
    op.drop_index(op.f("ix_project_library_created_at"), table_name="project_library")
    op.drop_index(op.f("ix_project_library_user_id"), table_name="project_library")
    op.drop_table("project_library")
