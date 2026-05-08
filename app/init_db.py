"""
Database schema initialization.

Replaces Alembic with a simpler approach:
1. create_all(checkfirst=True) creates tables that don't exist
2. migrations.sql applies idempotent ALTER statements for schema evolution
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import Base, engine

# Import all models so Base.metadata is fully populated
from app.models import (
    Dependency,
    Job,
    ProjectHistory,
    ProjectLibrary,
    User,
    UserPreference,
)

MIGRATIONS_SQL = Path(__file__).resolve().parent.parent / "migrations.sql"

# Reference models to ensure they are registered with Base.metadata
_MODELS = (User, UserPreference, ProjectLibrary, ProjectHistory, Job, Dependency)


async def init_db() -> None:
    """Create all tables and run migrations.sql."""
    # Step 1: Create tables that don't exist yet
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    # Step 2: Run migrations.sql if it exists and has content
    if MIGRATIONS_SQL.exists():
        sql_content = MIGRATIONS_SQL.read_text().strip()
        # Filter out empty lines and comments
        statements = [
            line.strip()
            for line in sql_content.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if statements:
            async with engine.begin() as conn:
                for stmt in statements:
                    await conn.execute(text(stmt))


def main() -> None:
    """Entry point for python -m app.init_db."""
    print("Initializing database schema...")
    asyncio.run(init_db())
    print("Schema initialization complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: Schema initialization failed: {e}", file=sys.stderr)
        sys.exit(1)
