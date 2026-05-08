.PHONY: help test lint format run setup clean migrate db-start db-stop db-reset db-status render neo4j-start neo4j-stop neo4j-status

UV := uv

# Detect OS for platform-specific commands
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    PSQL_CMD := psql
    CREATEDB_CMD := createdb
    DROPDB_CMD := dropdb
    DB_SERVICE_START := sudo systemctl start postgresql
    DB_SERVICE_STOP := sudo systemctl stop postgresql
    DB_SERVICE_STATUS := sudo systemctl status postgresql
endif
ifeq ($(UNAME_S),Darwin)
    PSQL_CMD := $(shell command -v psql || echo /opt/homebrew/opt/postgresql@14/bin/psql)
    CREATEDB_CMD := $(shell command -v createdb || echo /opt/homebrew/opt/postgresql@14/bin/createdb)
    DROPDB_CMD := $(shell command -v dropdb || echo /opt/homebrew/opt/postgresql@14/bin/dropdb)
    DB_SERVICE_START := brew services start postgresql@14
    DB_SERVICE_STOP := brew services stop postgresql@14
    DB_SERVICE_STATUS := brew services list | grep postgresql
endif

help:
	@echo "DependIQ"
	@echo ""
	@echo "  make test       Run all tests"
	@echo "  make lint       Check code for errors"
	@echo "  make format     Auto-format code"
	@echo "  make run        Start local server (handles all setup)"
	@echo "  make setup      First-time project setup"
	@echo "  make clean      Remove caches"
	@echo ""
	@echo "  make migrate    Run schema init (create tables + migrations.sql)"
	@echo "  make db-start   Start PostgreSQL"
	@echo "  make db-stop    Stop PostgreSQL"
	@echo "  make db-reset   Drop and recreate database (destructive)"
	@echo "  make db-status  Show database info"
	@echo "  make render     Render CLI (e.g. make render ARGS='services list')"

# === Primary targets — all standalone, zero setup required ===

test: clean _check-neo4j
	@$(UV) run pytest tests/ test_prompt_templates.py --ignore=tests/selenium --assert=plain

lint:
	@echo "Linting..."
	@$(UV) run ruff check .

format:
	@$(UV) run ruff format .
	@$(UV) run ruff check . --fix --exit-zero

run: _ensure-env _ensure-db
	@echo "Starting DependIQ on http://localhost:8000 ..."
	@$(UV) run uvicorn main:app --reload --host 0.0.0.0 --port 8000

setup: _ensure-env _ensure-db
	@echo ""
	@echo "Setup complete. Run 'make run' to start the server."

clean:
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name ".pytest_cache" -exec rm {} + 2>&1 || echo "No pytest cache"
	@find . -type d -name ".mypy_cache" -exec rm {} + 2>&1 || echo "No mypy cache"
	@find . -type d -name ".ruff_cache" -exec rm {} + 2>&1 || echo "No ruff cache"

# === Database schema ===

migrate:
	@$(UV) run python -m app.init_db

# === Internal targets (called by primary targets, not by humans) ===

_ensure-env:
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
		COOKIE_PW=$$($(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"); \
		sed -i '' "s|generate-with-python.*|$$COOKIE_PW|" .env 2>/dev/null || \
		sed -i "s|generate-with-python.*|$$COOKIE_PW|" .env; \
		echo ".env created with auto-generated WORKOS_COOKIE_PASSWORD."; \
		echo "Fill in WORKOS_API_KEY and WORKOS_CLIENT_ID from your WorkOS dashboard."; \
	fi

_ensure-db:
	@if ! command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		echo "ERROR: PostgreSQL not found."; \
		echo "  Install with: brew install postgresql@14"; \
		exit 1; \
	fi
	@$(DB_SERVICE_START) 2>/dev/null || (echo "ERROR: Could not start PostgreSQL. Run: $(DB_SERVICE_START)"; exit 1)
	@sleep 0.5
	@if ! $(PSQL_CMD) -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw dependiq; then \
		echo "Creating database 'dependiq'..."; \
		$(CREATEDB_CMD) dependiq || (echo "ERROR: Could not create database."; exit 1); \
	fi
	@$(UV) run python -m app.init_db || (echo "ERROR: Schema init failed. Run 'make db-reset' to start fresh."; exit 1)

# === Database management ===

db-start:
	@$(DB_SERVICE_START) 2>/dev/null && echo "PostgreSQL started" || \
		echo "Could not start PostgreSQL. Install with: brew install postgresql@14"

db-stop:
	@$(DB_SERVICE_STOP) 2>/dev/null && echo "PostgreSQL stopped" || \
		echo "Could not stop PostgreSQL."

db-reset:
	@echo "WARNING: This will delete all data and recreate the schema!"
	@read -p "Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(DROPDB_CMD) dependiq 2>&1 || echo "Note: database did not exist, creating fresh."; \
		$(CREATEDB_CMD) dependiq || (echo "ERROR: Could not create database."; exit 1); \
		$(UV) run python -m app.init_db || (echo "ERROR: Schema init failed."; exit 1); \
		echo "Database reset complete."; \
	else \
		echo "Cancelled"; \
	fi

db-status:
	@echo "Service:"
	@$(DB_SERVICE_STATUS) 2>/dev/null || echo "  Not running"
	@echo "Tables:"
	@$(PSQL_CMD) -d dependiq -c "\dt" 2>/dev/null || echo "  Not accessible"

# === Render CLI ===

ARGS ?=
render:
	@NO_PROXY= no_proxy= /opt/homebrew/bin/render $(ARGS)

# === Neo4j (local test instance via docker-compose) ===

neo4j-start:
	@docker compose up -d neo4j-test
	@echo "Waiting for Neo4j to be healthy..."
	@until docker compose exec -T neo4j-test cypher-shell -u neo4j -p dependiq_test_2026 "RETURN 1" >/dev/null 2>&1; do sleep 1; done
	@echo "Neo4j ready at bolt://localhost:7687"

neo4j-stop:
	@docker compose stop neo4j-test

neo4j-status:
	@docker ps --filter "name=dependiq-neo4j" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

_check-neo4j:
	@docker compose exec -T neo4j-test cypher-shell -u neo4j -p dependiq_test_2026 "RETURN 1" >/dev/null 2>&1 || \
		(echo "ERROR: Neo4j not running. Run: make neo4j-start"; exit 1)
