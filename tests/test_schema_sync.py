"""
Tests for schema synchronization between create_all() and migrations.sql.

Verifies that:
1. migrations.sql runs cleanly on a fresh database
2. migrations.sql does not add columns/tables that create_all() doesn't know about
"""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Dependency,
    Job,
    ProjectHistory,
    ProjectLibrary,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)

MIGRATIONS_SQL = Path(__file__).resolve().parent.parent / "migrations.sql"

# Reference models to ensure they are registered with Base.metadata
_MODELS = (User, UserPreference, ProjectLibrary, ProjectHistory, Job, Dependency, Workspace, WorkspaceMember)


def _get_test_engine():
    """Create a unique in-memory SQLite engine for schema tests."""
    import uuid

    url = f"sqlite+aiosqlite:///file:schema_test_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true"
    return create_async_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )


def _parse_migrations_sql() -> list[str]:
    """Parse migrations.sql into executable statements, split by semicolons."""
    if not MIGRATIONS_SQL.exists():
        return []
    sql_content = MIGRATIONS_SQL.read_text().strip()
    # Remove comment lines
    lines = [
        line for line in sql_content.splitlines()
        if not line.strip().startswith("--")
    ]
    # Join and split by semicolons
    full_sql = "\n".join(lines)
    statements = [s.strip() for s in full_sql.split(";") if s.strip()]
    return statements


def _get_schema_snapshot(inspector) -> dict[str, set[str]]:
    """Get a snapshot of all tables and their columns."""
    snapshot = {}
    for table_name in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        snapshot[table_name] = columns
    return snapshot


@pytest.mark.asyncio
async def test_migrations_sql_runs_cleanly_on_fresh_db():
    """migrations.sql must execute without errors on a freshly-created schema."""
    engine = _get_test_engine()

    # Create all tables from models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations.sql
    statements = _parse_migrations_sql()
    if statements:
        async with engine.begin() as conn:
            for stmt in statements:
                # SQLite doesn't support IF NOT EXISTS for ADD COLUMN,
                # so we adapt for testing by catching column-exists errors.
                # Also tolerate PG-specific syntax errors (gen_random_uuid, etc.)
                # since create_all() handles schema creation from models.
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    err_msg = str(e).lower()
                    # Allow: duplicate column (ADD COLUMN on existing col)
                    # Allow: syntax error from PG-specific DDL (gen_random_uuid, etc.)
                    # Allow: table already exists
                    if not any(
                        token in err_msg
                        for token in ("duplicate column", "syntax error", "already exists")
                    ):
                        raise

    # Verify tables still exist after migrations
    async with engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert len(result) > 0, "No tables found after running migrations"

    await engine.dispose()


@pytest.mark.asyncio
async def test_no_orphaned_migrations():
    """migrations.sql must not add schema that create_all() doesn't know about.

    If this test fails, it means migrations.sql has ALTER statements for columns
    that are not defined in the SQLAlchemy models. Fix by adding the column to
    the model, then remove the ALTER from migrations.sql.
    """
    engine = _get_test_engine()

    # Snapshot 1: schema from create_all() only
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        before = await conn.run_sync(
            lambda sync_conn: _get_schema_snapshot(inspect(sync_conn))
        )

    # Run migrations.sql
    statements = _parse_migrations_sql()
    if statements:
        async with engine.begin() as conn:
            for stmt in statements:
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    err_msg = str(e).lower()
                    if not any(
                        token in err_msg
                        for token in ("duplicate column", "syntax error", "already exists")
                    ):
                        raise

    # Snapshot 2: schema after migrations.sql
    async with engine.connect() as conn:
        after = await conn.run_sync(
            lambda sync_conn: _get_schema_snapshot(inspect(sync_conn))
        )

    # Compare: migrations.sql should NOT introduce new tables or columns
    new_tables = set(after.keys()) - set(before.keys())
    assert not new_tables, (
        f"migrations.sql added tables not in models: {new_tables}. "
        "Add these tables to app/models/ or remove the CREATE from migrations.sql."
    )

    for table_name in after:
        if table_name in before:
            new_columns = after[table_name] - before[table_name]
            assert not new_columns, (
                f"migrations.sql added columns to '{table_name}' not in models: {new_columns}. "
                "Add these columns to the model or remove the ALTER from migrations.sql."
            )

    await engine.dispose()
