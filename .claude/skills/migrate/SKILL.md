# Migrate Skill

Generate safe, idempotent schema migrations for DependIQ.

## When to invoke

- User says "add a column", "change the schema", "add a field to [model]"
- User modifies a SQLAlchemy model and needs the corresponding migration
- User says `/migrate`

## How DependIQ migrations work

There is NO Alembic. The system is:

1. **`app/models/*.py`** — SQLAlchemy models are the source of truth
2. **`app/init_db.py`** — runs `Base.metadata.create_all(checkfirst=True)` on startup (creates new tables)
3. **`migrations.sql`** — idempotent `ALTER TABLE` statements for column additions to existing tables
4. **`start.sh`** — runs `python -m app.init_db` before starting the app

### What create_all() handles automatically:
- New tables (CREATE TABLE IF NOT EXISTS)

### What requires a line in migrations.sql:
- Adding a column to an existing table
- Adding an index to an existing table
- Adding a constraint to an existing table

### What requires a manual script (rare):
- Dropping a column (destructive — confirm with user)
- Renaming a column (destructive — confirm with user)
- Data backfills

## Procedure

When the user wants to add/change schema:

### Step 1: Modify the model
Edit the SQLAlchemy model in `app/models/` to add the new column/field.

### Step 2: Generate the migration SQL
For each new column, add a line to `migrations.sql`:

```sql
-- 2026-05-08: Add [column] to [table] for [reason]
ALTER TABLE [table_name] ADD COLUMN IF NOT EXISTS [column_name] [type] [constraints];
```

Rules:
- Always use `IF NOT EXISTS` (Postgres 9.6+)
- Always include a date comment above the statement
- Use the exact column type from the SQLAlchemy model mapping:
  - `String` → `TEXT` (or `VARCHAR(n)`)
  - `Integer` → `INTEGER`
  - `Boolean` → `BOOLEAN`
  - `DateTime` → `TIMESTAMP`
  - `JSON` → `JSONB`
  - `UUID` → `UUID`
- Default values: `DEFAULT [value]`
- Nullable: omit `NOT NULL` (columns are nullable by default)
- Non-nullable with default: `NOT NULL DEFAULT [value]`
- Non-nullable without default: CANNOT be added to a table with existing rows (will fail). Must add as nullable first, backfill, then alter.

### Step 3: Verify
Run `make test` — the `test_schema_sync.py` tests will catch:
- migrations.sql that doesn't match the models (orphaned migrations)
- migrations.sql with syntax errors

### Step 4: Test locally
Run `make migrate` to apply the change to your local database.

## Examples

### Adding a nullable column:
```sql
-- 2026-05-08: Add avatar_url to users for profile pictures
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
```

### Adding a column with a default:
```sql
-- 2026-05-08: Add is_premium to users for billing
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT FALSE;
```

### Adding an index:
```sql
-- 2026-05-08: Index jobs by status for faster filtering
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
```

## Important constraints

- NEVER write `DROP COLUMN` without user confirmation
- NEVER write `ALTER COLUMN ... TYPE` without user confirmation (can lose data)
- ALWAYS run `make test` after modifying migrations.sql
- The `test_no_orphaned_migrations` test ensures migrations.sql doesn't diverge from models
- If adding a new TABLE (not column), just add the model — create_all() handles it, no migrations.sql needed
