# DependIQ — Dependency Intelligence

Analyze cross-project dependencies, map blast radius, and generate automated code modifications when dependencies change.

## Quick Start

```bash
# First-time setup (installs deps, starts Postgres + Neo4j, creates DB)
make setup

# Run the server
make run

# Run tests
make test
```

Every `make` target is self-sufficient — it starts whatever services it needs.

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Neo4j)
- PostgreSQL 14+ (`brew install postgresql@14` on macOS)

### Environment

`make setup` auto-creates `.env` from `.env.example`. You'll need to fill in:

```bash
WORKOS_API_KEY=sk_test_...       # From WorkOS dashboard
WORKOS_CLIENT_ID=client_...      # From WorkOS dashboard
ANTHROPIC_API_KEY=sk-ant-...     # For dependency analysis (or OPENAI_API_KEY)
```

## Development

```bash
make test       # Run all tests (auto-starts Neo4j)
make lint       # Check code (ruff)
make format     # Auto-format (ruff)
make run        # Start server on http://localhost:8000
```

### Database

```bash
make migrate    # Apply schema (create_all + migrations.sql)
make db-status  # Show service + table info
make db-reset   # Drop and recreate (destructive, prompts for confirmation)
```

### Neo4j

```bash
make neo4j-start   # Start test Neo4j via Docker
make neo4j-stop    # Stop Neo4j
make neo4j-status  # Show container status
```

### Render Deployment

```bash
make render ARGS='services list'    # Render CLI (proxy-bypassed)
make render ARGS='logs --resources srv-... --limit 20 --confirm'
```

## Architecture

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL + Neo4j
- **Frontend**: Jinja2 + HTMX + Tailwind CSS + Alpine.js (no React/build step)
- **Auth**: WorkOS AuthKit (GitHub, Google, Email OAuth)
- **LLM**: litellm (provider-agnostic — Claude, GPT, Ollama)
- **Graph**: Neo4j for cross-project dependency relationships + blast radius

## Project Structure

```
app/
  api/           — FastAPI routers (auth, workspaces, graph, blast_radius, etc.)
  models/        — SQLAlchemy models (User, Workspace, ProjectLibrary, etc.)
  graph/         — Neo4j connection + GraphService
  services/      — Pipeline, blast radius, relationships, LLM agent
  services/llm/  — Agent loop, model router, prompt templates
templates/       — Jinja2 (base.html, sign_in.html, workspaces.html)
tests/           — pytest suite
docker-compose.yml — Neo4j test instance
Makefile         — All dev commands (self-sufficient targets)
```

## Supported Projects

- **Python**: `requirements.txt`, `pyproject.toml`
- **Java/Scala**: `pom.xml`, `build.gradle`, `build.sbt`

## Documentation

- [`docs/database.md`](docs/database.md) — Schema and migration system
- [`docs/testing.md`](docs/testing.md) — Test strategy
- [`docs/themes.md`](docs/themes.md) — Theme system
- [`docs/accessibility.md`](docs/accessibility.md) — Accessibility features
- API docs: http://localhost:8000/docs (when running)
