---
name: Makefile Targets Must Fail Loudly
description: Never suppress errors with || true or 2>/dev/null on critical-path commands
type: feedback
---

When a Makefile target silently swallows errors (via `|| true` or `2>/dev/null`), downstream targets run against broken state. The user sees a cryptic runtime error instead of a clear build-time failure.

**Why:** The `_ensure-db` target originally had `alembic upgrade head 2>/dev/null || true`. This hid "Multiple heads" errors, letting `make run` start the server with no tables. Login then crashed with "Database Error" — hours of debugging.

**How to apply:** Critical commands (migrations, DB creation, service start) must exit non-zero on failure. Use `|| (echo "ERROR: ..."; exit 1)` instead of `|| true`. Only suppress errors on truly optional operations (like stopping an already-stopped service).
