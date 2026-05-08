.PHONY: help test lint format run setup clean migrate db-check db-start db-stop db-reset db-status render

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
	@echo "  make migrate MSG='...'  Generate migration from model changes"
	@echo "  make db-check   Verify migration chain integrity"
	@echo "  make db-start   Start PostgreSQL"
	@echo "  make db-stop    Stop PostgreSQL"
	@echo "  make db-reset   Drop and recreate database (destructive)"
	@echo "  make db-status  Show database info"
	@echo "  make render     Render CLI (e.g. make render ARGS='services list')"

# === Primary targets — all standalone, zero setup required ===

test: clean
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
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

# === Database migrations ===

migrate: db-check
	@if [ -z "$(MSG)" ]; then echo "ERROR: MSG is required. Usage: make migrate MSG=\"description\""; exit 1; fi
	@$(UV) run alembic revision --autogenerate -m "$(MSG)"
	@$(MAKE) db-check
	@echo "Migration created. Review it, then commit."

db-check:
	@HEADS=$$($(UV) run alembic heads 2>/dev/null | grep -c "^" || echo "0"); \
	if [ "$$HEADS" -gt 1 ]; then \
		echo "ERROR: Multiple migration heads detected ($$HEADS heads)."; \
		echo "  Fix: $(UV) run alembic merge heads -m \"merge\""; \
		exit 1; \
	fi
	@BAD=$$(find alembic/versions -name "*.py" ! -name "__*" -exec grep -L "auto generated" {} \; 2>/dev/null); \
	if [ -n "$$BAD" ]; then \
		echo "WARNING: Possibly hand-written migrations (missing autogenerate marker):"; \
		echo "$$BAD"; \
	fi

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
	@$(UV) run alembic upgrade head || (echo "ERROR: Migrations failed. Run 'make db-reset' to start fresh."; exit 1)

# === Database management ===

db-start:
	@$(DB_SERVICE_START) 2>/dev/null && echo "PostgreSQL started" || \
		echo "Could not start PostgreSQL. Install with: brew install postgresql@14"

db-stop:
	@$(DB_SERVICE_STOP) 2>/dev/null && echo "PostgreSQL stopped" || \
		echo "Could not stop PostgreSQL."

db-reset:
	@echo "WARNING: This will delete all data and regenerate migrations!"
	@read -p "Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(DROPDB_CMD) dependiq 2>/dev/null || true; \
		$(CREATEDB_CMD) dependiq; \
		rm -f alembic/versions/*.py; \
		$(UV) run alembic revision --autogenerate -m "baseline schema"; \
		$(UV) run alembic upgrade head; \
		echo "Database reset complete with fresh baseline migration."; \
	else \
		echo "Cancelled"; \
	fi

db-status:
	@echo "Service:"
	@$(DB_SERVICE_STATUS) 2>/dev/null || echo "  Not running"
	@echo "Tables:"
	@$(PSQL_CMD) -d dependiq -c "\dt" 2>/dev/null || echo "  Not accessible"
	@echo "Migration:"
	@$(UV) run alembic current 2>/dev/null || echo "  None applied"

# === Render CLI ===

ARGS ?=
render:
	@NO_PROXY= no_proxy= /opt/homebrew/bin/render $(ARGS)
