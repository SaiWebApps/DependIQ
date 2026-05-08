---
name: Never Hand-Write Migrations
description: Alembic revision IDs must be auto-generated; hand-writing them breaks the migration chain
type: feedback
---

Never hand-write alembic migration files. Always use `make migrate MSG="description"` which runs `alembic revision --autogenerate`.

**Why:** A previous session invented fake revision IDs (a1b2c3d4e5f6, g4h5i6j7k8l9) that broke the migration chain with "Multiple heads" errors. g4h5i6j7k8l9 isn't even valid hex. This blocked the app from starting for hours.

**How to apply:** The prevent-laziness.sh hook blocks writes to alembic/versions/. The only sanctioned command is `make migrate MSG="..."`. If the chain is broken, use `make db-reset`.
