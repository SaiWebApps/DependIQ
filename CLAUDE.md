# DependIQ Project Rules

## Render Deployment

> **STOP. Before ANY push to main:** Run `make verify-deploy`. If it fails, DO NOT push.

> **NEVER use `generateValue: true`** in render.yaml for secrets (JWT, session, etc.). It regenerates on every blueprint sync, killing all user sessions.

> **NEVER ask the user to manually enter env vars.** Use `make render` or `curl` to the Render API. The API key is in `~/.render/cli.yaml`.

> **"Deploy is live" ≠ "Bug is fixed."** After deploy, check logs (`make render ARGS="logs --resources srv-... --limit 20 --confirm"`) for errors. Report evidence, not status.

## Build Verification

> **After modifying `requirements.txt`, `build.sh`, or `pyproject.toml`:** Run `make verify-deploy` to simulate Render's build locally before pushing.

## Auth / Cookies

> **Cookie `path` must always be `/`.** Without it, cookies set from `/api/auth/...` callbacks are scoped to that path and invisible to page routes.

> **UUID columns require `uuid.UUID()` conversion** before SQLAlchemy WHERE clauses with asyncpg. String comparison silently returns no rows.

## Meetings

> **When the user requests `/meeting`, run ALL 10 layers.** Do not skip, abbreviate, or argue it's unnecessary. The adversarial process catches root causes that quick fixes miss.
