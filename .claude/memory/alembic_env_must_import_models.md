---
name: Alembic env.py Must Import Models
description: Alembic autogenerate produces empty migrations if model classes aren't imported in env.py
type: feedback
---

Alembic's `--autogenerate` compares `Base.metadata` against the database. If the model classes haven't been imported, `Base.metadata.tables` is empty and autogenerate produces `pass` (empty migration).

**Why:** SQLAlchemy models register themselves with Base.metadata at import time. No import = no registration = autogenerate sees nothing.

**How to apply:** In `alembic/env.py`, always have `import app.models` after importing Base. This ensures all model classes are loaded before autogenerate runs.
