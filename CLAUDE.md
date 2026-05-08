# DependIQ Project Rules

> **STOP. Read `.claude/memory/MEMORY.md` before starting any work.** It contains hard-won lessons from previous sessions. Violating a documented lesson is a CRITICAL failure.

## Diagnosis Before Code

> **STOP. Before writing or rewriting ANY code:** Run a diagnostic command first. `curl` the URL. Query the API. Check the logs. Read the error. If you cannot state the ROOT CAUSE with evidence from a command output, you are NOT ready to write code.

> **STOP. NEVER declare "it works" or "fixed" without evidence.** Evidence = `make test` output showing all green, OR a browser screenshot, OR a curl response. "The code looks correct" is NOT evidence.

> **STOP. NEVER suggest switching tools/libraries until you have exhausted diagnosis of the current one.** Run diagnostics, curl endpoints, write test scripts. "It doesn't work" without a specific error message and root cause = you haven't tried hard enough.

> **STOP. NEVER blame external configuration without API-level proof.** Use curl, SDK management APIs, or diagnostic scripts to verify claims. If you cannot access the system to verify, say "I cannot verify this" — do not say "your config is wrong."

## Render Deployment

> **STOP. Before ANY push to main:** Run `make test`. If it fails, DO NOT push.

> **NEVER use `generateValue: true`** in render.yaml for secrets (JWT, session, etc.). It regenerates on every blueprint sync, killing all user sessions.

> **NEVER ask the user to manually enter env vars.** Use `make render` or `curl` to the Render API. The API key is in `~/.render/cli.yaml`.

> **"Deploy is live" ≠ "Bug is fixed."** After deploy, check logs (`make render ARGS="logs --resources srv-... --limit 20 --confirm"`) for errors. Report evidence, not status.

## Build Verification

> **After modifying `requirements.txt`, `build.sh`, or `pyproject.toml`:** Run `make test` to verify nothing broke before pushing.

## Auth / Cookies

> **Cookie `path` must always be `/`.** Without it, cookies set from `/api/auth/...` callbacks are scoped to that path and invisible to page routes.

> **UUID columns require `uuid.UUID()` conversion** before SQLAlchemy WHERE clauses with asyncpg. String comparison silently returns no rows.

> **WorkOS direct OAuth (provider=GitHubOAuth) works. AuthKit hosted UI (provider=authkit) requires sign-in endpoint to match origin.** For local dev, use direct OAuth only.

> **Before touching auth code, curl the authorize URL first.** `curl -s -o /dev/null -w "%{http_code} %{redirect_url}" "URL"` — if 302 to provider, infrastructure works. The bug is elsewhere.

## Database Schema

> **There is NO Alembic.** Migrations use `create_all()` + idempotent SQL. See `/migrate` skill for full docs.

> **New table?** Add the model to `app/models/`. `create_all(checkfirst=True)` handles it automatically on next deploy.

> **New column on existing table?** Edit the model FIRST, then add one line to `migrations.sql`: `ALTER TABLE x ADD COLUMN IF NOT EXISTS y type;`

> **Run `make test` after any schema change.** The `test_schema_sync.py` tests catch mismatches between models and `migrations.sql`.

> **Run `make migrate` to apply locally.** It runs `python -m app.init_db` which does `create_all()` + `migrations.sql`.

> **NEVER write DROP or RENAME without user confirmation.** These are destructive and irreversible.

> **To start fresh locally:** `make db-reset` drops and recreates everything from models.

## Makefile

> **NEVER use `|| true` or `2>/dev/null` on critical-path commands.** If a migration, DB creation, or service start fails, the Makefile MUST exit non-zero. Use `|| (echo "ERROR: ..."; exit 1)`.

> **`make lint` proves NOTHING about behavior.** Only `make test` (full suite, 312+ tests) proves correctness.

## Meetings

> **When the user requests `/meeting`, run ALL 10 layers.** Do not skip, abbreviate, or argue it's unnecessary. The adversarial process catches root causes that quick fixes miss.
