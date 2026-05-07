.PHONY: help sync format lint typecheck test test-unit test-integration test-functional test-llm test-llm-integration test-coverage test-quick clean run dev setup db-setup db-create db-migrate db-reset db-status db-start db-stop render

# uv is the only package manager. No pip, no venv activation.
UV := uv

# Detect OS for platform-specific commands
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    OS := Linux
    PSQL_CMD := psql
    CREATEDB_CMD := createdb
    DROPDB_CMD := dropdb
    DB_SERVICE_START := sudo systemctl start postgresql
    DB_SERVICE_STOP := sudo systemctl stop postgresql
    DB_SERVICE_STATUS := sudo systemctl status postgresql
endif
ifeq ($(UNAME_S),Darwin)
    OS := macOS
    PSQL_CMD := $(shell command -v psql || echo /opt/homebrew/opt/postgresql@14/bin/psql)
    CREATEDB_CMD := $(shell command -v createdb || echo /opt/homebrew/opt/postgresql@14/bin/createdb)
    DROPDB_CMD := $(shell command -v dropdb || echo /opt/homebrew/opt/postgresql@14/bin/dropdb)
    DB_SERVICE_START := brew services start postgresql@14
    DB_SERVICE_STOP := brew services stop postgresql@14
    DB_SERVICE_STATUS := brew services list | grep postgresql
endif

help:
	@echo "Available commands:"
	@echo ""
	@echo "  sync            - Install/sync all dependencies (uv sync)"
	@echo "  format          - Format code (ruff format + ruff check --fix)"
	@echo "  lint            - Check for errors (ruff check)"
	@echo "  typecheck       - Run mypy"
	@echo "  test            - Run all tests (except selenium)"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-llm        - Run LLM agent layer tests"
	@echo "  test-llm-integration - Run LLM tests against live registries"
	@echo "  test-integration- Run API integration tests"
	@echo "  test-functional - Run functional tests"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  test-quick      - Run tests excluding slow"
	@echo "  run             - Start dev server (uvicorn --reload)"
	@echo "  dev             - Alias for run"
	@echo "  setup           - First-time setup (sync + db)"
	@echo "  clean           - Remove caches and bytecode"
	@echo ""
	@echo "  db-setup        - Start postgres, create db, run migrations"
	@echo "  db-start        - Start PostgreSQL"
	@echo "  db-stop         - Stop PostgreSQL"
	@echo "  db-create       - Create dependiq database"
	@echo "  db-migrate      - Run alembic migrations"
	@echo "  db-reset        - Drop and recreate database"
	@echo "  db-status       - Show database info"

# Dependency management — single command
sync:
	@echo "Installing dependencies..."
	$(UV) sync
	@echo "Done."

# Formatting — ruff does both formatting and import sorting
format:
	@echo "Formatting..."
	@$(UV) run ruff format .
	@$(UV) run ruff check . --fix --exit-zero
	@echo "Done."

# Linting
lint:
	@echo "Linting..."
	$(UV) run ruff check .

# Type checking
typecheck:
	@echo "Type checking..."
	$(UV) run mypy main.py

# Tests
test: clean
	@echo "Running all tests..."
	$(UV) run pytest tests/ test_prompt_templates.py --ignore=tests/selenium --assert=plain

test-unit: clean
	@echo "Running unit tests..."
	$(UV) run pytest tests/test_utils.py tests/test_services.py tests/test_middleware.py tests/test_models.py test_prompt_templates.py --assert=plain

test-llm:
	@echo "Running LLM agent layer tests..."
	$(UV) run pytest tests/llm/ -m "not integration"

test-llm-integration:
	@echo "Running LLM integration tests (hits live registries)..."
	$(UV) run pytest tests/llm/ -m "integration"

test-integration: clean
	@echo "Running integration tests..."
	$(UV) run pytest tests/test_api_integration.py tests/test_auth_integration.py tests/test_user_profile.py --assert=plain

test-functional: clean
	@echo "Running functional tests..."
	$(UV) run pytest tests/test_functional.py --assert=plain

test-coverage: clean
	@echo "Running tests with coverage..."
	$(UV) run pytest tests/ test_prompt_templates.py --cov=app --cov-report=html --cov-report=term-missing --assert=plain --ignore=tests/selenium
	@echo "Open htmlcov/index.html for the report."

test-quick: clean
	@echo "Running quick tests..."
	$(UV) run pytest tests/ test_prompt_templates.py -m "not slow" --assert=plain --ignore=tests/selenium

# Application
run:
	@echo "Starting DependIQ on http://localhost:8000 ..."
	$(UV) run uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev: run

# Setup
setup: sync db-setup
	@echo ""
	@echo "Setup complete. Run 'make run' to start."

# Clean
clean:
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

# Database management
db-setup: db-start db-create db-migrate
	@echo "Database ready."

db-start:
	@echo "Starting PostgreSQL ($(OS))..."
	@$(DB_SERVICE_START) 2>/dev/null && echo "PostgreSQL started" || \
		echo "Could not start PostgreSQL. Start it manually."

db-stop:
	@echo "Stopping PostgreSQL ($(OS))..."
	@$(DB_SERVICE_STOP) 2>/dev/null && echo "PostgreSQL stopped" || \
		echo "Could not stop PostgreSQL. Stop it manually."

db-create:
	@echo "Creating dependiq database..."
	@if command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		if $(PSQL_CMD) -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw dependiq; then \
			echo "Database 'dependiq' already exists"; \
		else \
			$(CREATEDB_CMD) dependiq 2>/dev/null && echo "Database 'dependiq' created" || \
			echo "Could not create database. Run: $(CREATEDB_CMD) dependiq"; \
		fi \
	else \
		echo "psql not found. Create database manually: $(CREATEDB_CMD) dependiq"; \
	fi

db-migrate:
	@echo "Running migrations..."
	@if [ ! -d "alembic/versions" ] || [ -z "$$(ls -A alembic/versions 2>/dev/null)" ]; then \
		echo "Generating initial migration..."; \
		$(UV) run alembic revision --autogenerate -m "Initial migration"; \
	fi
	@$(UV) run alembic upgrade head && echo "Migrations applied"

db-reset:
	@echo "WARNING: This will delete all data!"
	@read -p "Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(DROPDB_CMD) dependiq 2>/dev/null || true; \
		$(MAKE) db-create; \
		$(MAKE) db-migrate; \
		echo "Database reset complete"; \
	else \
		echo "Cancelled"; \
	fi

db-status:
	@echo "Database Status ($(OS))"
	@echo "---"
	@echo "Service:"
	@$(DB_SERVICE_STATUS) 2>/dev/null || echo "  Status check unavailable"
	@echo ""
	@echo "Tables:"
	@if command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		$(PSQL_CMD) -d dependiq -c "\dt" 2>/dev/null || \
		echo "  Database not accessible"; \
	else \
		echo "  psql not found"; \
	fi
	@echo ""
	@echo "Migration:"
	@$(UV) run alembic current 2>/dev/null || echo "  No migrations applied"

# Render CLI — clears NO_PROXY so Go httpproxy routes through corporate proxy.
# Examples: make render ARGS="services list"
#           make render ARGS="deploys list --service srv-d7u2itjbc2fs73f1tb40"
ARGS ?=
render:
	@NO_PROXY= no_proxy= /opt/homebrew/bin/render $(ARGS)
