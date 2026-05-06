.PHONY: help install install-dev format lint typecheck pre-commit test test-unit test-integration test-functional test-selenium test-selenium-headless test-coverage test-quick test-llm quality clean run dev setup github db-setup db-create db-migrate db-reset db-status db-start db-stop pre-commit-install pre-commit-run docker-build docs check-python

# Python version requirements
PYTHON_MIN_VERSION := 3.11
PYTHON_MAX_VERSION := 3.12
PYTHON := $(shell command -v python3.12 || command -v python3.11 || command -v python3)
VENV_BIN := .venv/bin
PIP := $(VENV_BIN)/pip
PYTHON_VENV := $(VENV_BIN)/python

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
    # Try common PostgreSQL paths on macOS
    PSQL_CMD := $(shell command -v psql || echo /opt/homebrew/opt/postgresql@14/bin/psql || echo /usr/local/opt/postgresql@14/bin/psql)
    CREATEDB_CMD := $(shell command -v createdb || echo /opt/homebrew/opt/postgresql@14/bin/createdb || echo /usr/local/opt/postgresql@14/bin/createdb)
    DROPDB_CMD := $(shell command -v dropdb || echo /opt/homebrew/opt/postgresql@14/bin/dropdb || echo /usr/local/opt/postgresql@14/bin/dropdb)
    DB_SERVICE_START := brew services start postgresql@14
    DB_SERVICE_STOP := brew services stop postgresql@14
    DB_SERVICE_STATUS := brew services list | grep postgresql
endif

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "🚀 Getting Started (New Users):"
	@echo "  run             - Run the application (auto-setup on first run)"
	@echo "  setup           - Complete setup (install, database, pre-commit)"
	@echo ""
	@echo "📦 Installation:"
	@echo "  install         - Install production dependencies"
	@echo "  install-dev     - Install development dependencies"
	@echo ""
	@echo "🗄️  Database:"
	@echo "  db-setup        - Complete database setup (start, create, migrate)"
	@echo "  db-start        - Start PostgreSQL service"
	@echo "  db-stop         - Stop PostgreSQL service"
	@echo "  db-create       - Create the dependiq database"
	@echo "  db-migrate      - Run database migrations"
	@echo "  db-reset        - Reset database (drop and recreate)"
	@echo "  db-status       - Show database status and tables"
	@echo ""
	@echo "🎨 Code Quality:"
	@echo "  pre-commit      - Run pre-commit hooks (format, lint, typecheck, file checks)"
	@echo "  format          - Format code with black, isort, and ruff"
	@echo "  lint            - Run linting with ruff"
	@echo "  typecheck       - Run type checking with mypy"
	@echo "  quality         - Run all quality checks (pre-commit + tests)"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test            - Run all tests with auto-started server (headless Selenium)"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-integration- Run integration tests only"
	@echo "  test-functional - Run functional tests only"
	@echo "  test-selenium   - Run Selenium tests with visible browser (auto-starts server)"
	@echo "  test-selenium-headless - Run Selenium tests in headless mode (auto-starts server)"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  test-quick      - Run quick tests (exclude slow)"
	@echo ""
	@echo "🚀 Application:"
	@echo "  run             - Run the FastAPI application"
	@echo "  dev             - Run the application in development mode"
	@echo ""
	@echo "🔧 Other:"
	@echo "  github          - Setup GitHub OAuth integration"
	@echo "  clean           - Clean up generated files"

# Check Python version
check-python:
	@echo "🐍 Checking Python version..."
	@if ! command -v $(PYTHON) >/dev/null 2>&1; then \
		echo "❌ Error: Python 3 not found"; \
		echo "Please install Python $(PYTHON_MIN_VERSION) or $(PYTHON_MAX_VERSION)"; \
		exit 1; \
	fi
	@PYTHON_VERSION=$$($(PYTHON) -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'); \
	PYTHON_MAJOR=$$(echo $$PYTHON_VERSION | cut -d. -f1); \
	PYTHON_MINOR=$$(echo $$PYTHON_VERSION | cut -d. -f2); \
	MIN_MAJOR=$$(echo $(PYTHON_MIN_VERSION) | cut -d. -f1); \
	MIN_MINOR=$$(echo $(PYTHON_MIN_VERSION) | cut -d. -f2); \
	MAX_MAJOR=$$(echo $(PYTHON_MAX_VERSION) | cut -d. -f1); \
	MAX_MINOR=$$(echo $(PYTHON_MAX_VERSION) | cut -d. -f2); \
	if [ $$PYTHON_MAJOR -lt $$MIN_MAJOR ] || ([ $$PYTHON_MAJOR -eq $$MIN_MAJOR ] && [ $$PYTHON_MINOR -lt $$MIN_MINOR ]); then \
		echo "❌ Error: Python $$PYTHON_VERSION found, but $(PYTHON_MIN_VERSION)-$(PYTHON_MAX_VERSION) is required"; \
		echo "Please install Python $(PYTHON_MIN_VERSION) or $(PYTHON_MAX_VERSION)"; \
		exit 1; \
	fi; \
	if [ $$PYTHON_MAJOR -gt $$MAX_MAJOR ] || ([ $$PYTHON_MAJOR -eq $$MAX_MAJOR ] && [ $$PYTHON_MINOR -gt $$MAX_MINOR ]); then \
		echo "❌ Error: Python $$PYTHON_VERSION found, but $(PYTHON_MIN_VERSION)-$(PYTHON_MAX_VERSION) is required"; \
		echo "Python 3.13+ is not yet fully supported. Please install Python $(PYTHON_MIN_VERSION) or $(PYTHON_MAX_VERSION)"; \
		exit 1; \
	fi
	@echo "✅ Python $$PYTHON_VERSION detected ($(OS))"

# Installation targets
install: check-python
	@if [ ! -d ".venv" ]; then \
		echo "📦 Creating virtual environment..."; \
		$(PYTHON) -m venv .venv; \
	fi
	@echo "📦 Installing production dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "✅ Installation complete!"

install-dev: check-python
	@if [ ! -d ".venv" ]; then \
		echo "📦 Creating virtual environment..."; \
		$(PYTHON) -m venv .venv; \
	fi
	@echo "📦 Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e ".[dev]"
	$(VENV_BIN)/pre-commit install
	@echo "✅ Development environment setup complete!"

# Code formatting
format:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	fi
	@echo "🎨 Formatting code with black, isort, and ruff..."
	@$(PYTHON_VENV) -m black . 2>&1 | grep -v "All done\|files left unchanged" || true
	@$(PYTHON_VENV) -m isort . 2>&1 | grep -v "Skipped\|files left unchanged" || true
	@echo "🔧 Auto-fixing ruff issues..."
	@$(PYTHON_VENV) -m ruff check . --fix --exit-zero
	@echo "🔍 Checking for remaining ruff issues..."
	@if ! $(PYTHON_VENV) -m ruff check . --quiet; then \
		echo ""; \
		echo "❌ Ruff found issues that couldn't be auto-fixed:"; \
		echo ""; \
		$(PYTHON_VENV) -m ruff check .; \
		echo ""; \
		echo "💡 Please fix these issues before running tests"; \
		exit 1; \
	fi
	@echo "✅ Code formatting complete - no issues found!"

# Linting
lint:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	fi
	@echo "🔍 Running linter..."
	$(PYTHON_VENV) -m ruff check .
	@echo "✅ Linting complete!"

# Type checking
typecheck:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	fi
	@echo "🔬 Running type checker..."
	$(PYTHON_VENV) -m mypy main.py prompt_templates.py
	@echo "✅ Type checking complete!"

# Pre-commit checks (formatting, linting, type checking, file validation)
pre-commit:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	fi
	@echo "🔍 Running pre-commit checks (formatting, linting, type checking, file validation)..."
	@$(VENV_BIN)/pre-commit run --all-files || { echo "❌ Pre-commit checks failed"; exit 1; }
	@echo "✅ Pre-commit checks passed!"

# Check if pre-commit hooks are installed
check-hooks:
	@if [ ! -f ".git/hooks/pre-commit" ] || ! grep -q "pre-commit" ".git/hooks/pre-commit" 2>/dev/null; then \
		echo "⚠️  Pre-commit hooks not installed!"; \
		echo "📦 Installing pre-commit hooks to catch issues automatically..."; \
		$(MAKE) pre-commit-install; \
	fi

# Testing
test: check-hooks clean format
	@echo ""
	@echo "🧪 Running all tests (unit, integration, functional, and Selenium in headless mode)..."
	@echo "🚀 Starting application in background for Selenium tests..."
	@$(VENV_BIN)/uvicorn main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 & echo $$! > .test_server.pid
	@sleep 3
	@echo "✅ Application started"
	@echo "💡 To run Selenium with visible browser: make test-selenium"
	@echo ""
	@HEADLESS=true $(PYTHON_VENV) -m pytest tests/ test_prompt_templates.py -v --tb=short --assert=plain; \
	EXIT_CODE=$$?; \
	echo ""; \
	echo "🛑 Stopping test server..."; \
	if [ -f .test_server.pid ]; then \
		kill `cat .test_server.pid` 2>/dev/null || true; \
		rm .test_server.pid; \
	fi; \
	if [ $$EXIT_CODE -eq 0 ]; then \
		echo "✅ All tests complete!"; \
	else \
		echo "❌ Some tests failed"; \
	fi; \
	exit $$EXIT_CODE

test-unit: check-hooks clean format
	@echo ""
	@echo "🧪 Running unit tests..."
	$(PYTHON_VENV) -m pytest tests/test_utils.py tests/test_services.py tests/test_middleware.py tests/test_models.py test_prompt_templates.py -v --assert=plain
	@echo "✅ Unit tests complete!"

test-llm:
	@echo ""
	@echo "🧪 Running LLM agent layer tests..."
	/opt/homebrew/bin/uv run pytest tests/llm/ -v --tb=short -m "not integration"
	@echo "✅ LLM tests complete!"

test-llm-integration:
	@echo ""
	@echo "🌐 Running LLM integration tests (hits live registries)..."
	/opt/homebrew/bin/uv run pytest tests/llm/ -v --tb=short -m "integration"
	@echo "✅ LLM integration tests complete!"

test-integration: check-hooks clean format
	@echo ""
	@echo "🧪 Running integration tests..."
	$(PYTHON_VENV) -m pytest tests/test_api_integration.py tests/test_auth_integration.py tests/test_user_profile.py -v --assert=plain
	@echo "✅ Integration tests complete!"

test-functional: check-hooks clean format
	@echo ""
	@echo "🧪 Running functional tests..."
	$(PYTHON_VENV) -m pytest tests/test_functional.py -v --assert=plain
	@echo "✅ Functional tests complete!"

test-selenium: check-hooks clean format
	@echo ""
	@echo "🌐 Running Selenium end-to-end tests (with visible browser)..."
	@echo "🚀 Starting application in background..."
	@$(VENV_BIN)/uvicorn main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 & echo $$! > .test_server.pid
	@sleep 3
	@echo "✅ Application started"
	@echo ""
	@$(PYTHON_VENV) -m pytest tests/selenium/ -v --tb=short; \
	EXIT_CODE=$$?; \
	echo ""; \
	echo "🛑 Stopping test server..."; \
	if [ -f .test_server.pid ]; then \
		kill `cat .test_server.pid` 2>/dev/null || true; \
		rm .test_server.pid; \
	fi; \
	if [ $$EXIT_CODE -eq 0 ]; then \
		echo "✅ Selenium tests complete!"; \
	else \
		echo "❌ Some tests failed"; \
	fi; \
	exit $$EXIT_CODE

test-selenium-headless: check-hooks clean format
	@echo ""
	@echo "🌐 Running Selenium tests in headless mode..."
	@echo "🚀 Starting application in background..."
	@$(VENV_BIN)/uvicorn main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 & echo $$! > .test_server.pid
	@sleep 3
	@echo "✅ Application started"
	@echo ""
	@HEADLESS=true $(PYTHON_VENV) -m pytest tests/selenium/ -v --tb=short; \
	EXIT_CODE=$$?; \
	echo ""; \
	echo "🛑 Stopping test server..."; \
	if [ -f .test_server.pid ]; then \
		kill `cat .test_server.pid` 2>/dev/null || true; \
		rm .test_server.pid; \
	fi; \
	if [ $$EXIT_CODE -eq 0 ]; then \
		echo "✅ Selenium tests complete!"; \
	else \
		echo "❌ Some tests failed"; \
	fi; \
	exit $$EXIT_CODE

test-coverage: check-hooks clean format
	@echo ""
	@echo "🧪 Running tests with coverage..."
	$(PYTHON_VENV) -m pytest tests/ test_prompt_templates.py --cov=app --cov-report=html --cov-report=term-missing --assert=plain --ignore=tests/selenium
	@echo "✅ Tests complete! Open htmlcov/index.html to view coverage report."

test-quick: check-hooks clean format
	@echo ""
	@echo "🧪 Running quick tests (excluding slow)..."
	$(PYTHON_VENV) -m pytest tests/ test_prompt_templates.py -v -m "not slow" --assert=plain --ignore=tests/selenium
	@echo "✅ Quick tests complete!"

# Run all quality checks
quality: check-hooks format test
	@echo "✅ All quality checks passed!"

# Clean up
clean:
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@echo "✅ Cleanup complete!"

# Application targets
run: format
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  First-time setup required!"; \
		echo ""; \
		echo "Running complete setup..."; \
		echo ""; \
		$(MAKE) setup; \
		echo ""; \
		echo "✅ Setup complete!"; \
		echo ""; \
	fi
	@echo "🚀 Starting dependiq application..."
	@echo "📡 Server will be available at http://localhost:8000"
	@$(VENV_BIN)/uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev: run

# Complete setup for new developers
setup: install-dev db-setup format
	@echo "🎉 Project setup complete!"
	@echo ""
	@echo "✅ Dependencies installed"
	@echo "✅ Database configured"
	@echo "✅ Code formatted"
	@echo "✅ Pre-commit hooks installed"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run 'make run' to start the application"
	@echo "  2. Visit http://localhost:8000"
	@echo "  3. Run 'make quality' to run all checks"

# Database management
db-setup: db-start db-create db-migrate
	@echo ""
	@echo "✅ Database setup complete!"
	@echo "   - PostgreSQL is running"
	@echo "   - Database 'dependiq' created"
	@echo "   - Migrations applied"
	@echo ""
	@echo "Run 'make db-status' to verify"

db-start:
	@echo "🗄️  Starting PostgreSQL ($(OS))..."
	@$(DB_SERVICE_START) 2>/dev/null && echo "✅ PostgreSQL started" || \
		echo "⚠️  Could not start PostgreSQL. Please start it manually"

db-stop:
	@echo "🗄️  Stopping PostgreSQL ($(OS))..."
	@$(DB_SERVICE_STOP) 2>/dev/null && echo "✅ PostgreSQL stopped" || \
		echo "⚠️  Could not stop PostgreSQL. Please stop it manually"

db-create:
	@echo "🗄️  Creating dependiq database..."
	@if command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		if $(PSQL_CMD) -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw dependiq; then \
			echo "✅ Database 'dependiq' already exists"; \
		else \
			$(CREATEDB_CMD) dependiq 2>/dev/null && echo "✅ Database 'dependiq' created" || \
			echo "⚠️  Could not create database. Please run: $(CREATEDB_CMD) dependiq"; \
		fi \
	else \
		echo "⚠️  psql not found. Create database manually: $(CREATEDB_CMD) dependiq"; \
	fi

db-migrate:
	@echo "🗄️  Running database migrations..."
	@if [ ! -d "alembic/versions" ] || [ -z "$$(ls -A alembic/versions 2>/dev/null)" ]; then \
		echo "📝 Generating initial migration..."; \
		$(PYTHON_VENV) -m alembic revision --autogenerate -m "Initial migration"; \
	fi
	@$(PYTHON_VENV) -m alembic upgrade head && echo "✅ Migrations applied successfully"

db-reset:
	@echo "⚠️  WARNING: This will delete all data in the database!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "🗄️  Resetting database..."; \
		$(DROPDB_CMD) dependiq 2>/dev/null || true; \
		$(MAKE) db-create; \
		$(MAKE) db-migrate; \
		echo "✅ Database reset complete"; \
	else \
		echo "❌ Database reset cancelled"; \
	fi

db-status:
	@echo "🗄️  Database Status ($(OS))"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "PostgreSQL Service:"
	@$(DB_SERVICE_STATUS) 2>/dev/null || echo "  Status check unavailable"
	@echo ""
	@echo "Databases:"
	@if command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		$(PSQL_CMD) -l 2>/dev/null | grep dependiq || echo "  Could not list databases"; \
	else \
		echo "  psql not found"; \
	fi
	@echo ""
	@echo "Tables in 'dependiq' database:"
	@if command -v $(PSQL_CMD) >/dev/null 2>&1; then \
		$(PSQL_CMD) -d dependiq -c "\dt" 2>/dev/null || \
		echo "  Database 'dependiq' not found or not accessible"; \
	else \
		echo "  psql not found"; \
	fi
	@echo ""
	@echo "Migration Status:"
	@$(PYTHON_VENV) -m alembic current 2>/dev/null || echo "  No migrations applied"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# GitHub OAuth setup
github:
	@echo "🔐 GitHub OAuth Setup"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "First, create a GitHub OAuth App:"
	@echo "  👉 https://github.com/settings/developers"
	@echo "     - Click 'New OAuth App'"
	@echo "     - Homepage URL: http://localhost:8000"
	@echo "     - Callback URL: http://localhost:8000/auth/github/callback"
	@echo ""
	@bash -c ' \
		read -p "Enter GitHub Client ID: " client_id; \
		read -p "Enter GitHub Client Secret: " client_secret; \
		secret_key=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))"); \
		echo ""; \
		echo "💾 Updating .env file..."; \
		touch .env; \
		grep -v "^GITHUB_CLIENT_ID=" .env > .env.tmp 2>/dev/null || true; \
		grep -v "^GITHUB_CLIENT_SECRET=" .env.tmp > .env.tmp2 2>/dev/null || true; \
		grep -v "^GITHUB_REDIRECT_URI=" .env.tmp2 > .env.tmp3 2>/dev/null || true; \
		grep -v "^SECRET_KEY=" .env.tmp3 > .env.tmp4 2>/dev/null || true; \
		mv .env.tmp4 .env 2>/dev/null || true; \
		rm -f .env.tmp .env.tmp2 .env.tmp3 2>/dev/null || true; \
		echo "" >> .env; \
		echo "# GitHub OAuth Configuration" >> .env; \
		echo "GITHUB_CLIENT_ID=$$client_id" >> .env; \
		echo "GITHUB_CLIENT_SECRET=$$client_secret" >> .env; \
		echo "GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback" >> .env; \
		echo "SECRET_KEY=$$secret_key" >> .env; \
		echo ""; \
		echo "✅ GitHub OAuth configured successfully!"; \
		echo "🚀 Restart the server with: make run"; \
	'
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Pre-commit targets
pre-commit-install:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	else \
		echo "📦 Installing pre-commit hooks for git..."; \
		$(VENV_BIN)/pre-commit install; \
		$(VENV_BIN)/pre-commit install --hook-type pre-push; \
		echo "✅ Pre-commit hooks installed!"; \
		echo "   - Hooks will run automatically on 'git commit'"; \
		echo "   - Format checks will run on 'git push'"; \
		echo ""; \
		echo "💡 To run hooks manually: make pre-commit-run"; \
	fi

pre-commit-run:
	@if [ ! -d ".venv" ]; then \
		echo "⚠️  Virtual environment not found. Running install-dev..."; \
		$(MAKE) install-dev; \
	fi
	$(PYTHON_VENV) -m pre_commit run --all-files
	@echo "✅ Pre-commit checks complete!"

# Docker-related (future expansion)
docker-build:
	@echo "🐳 Docker support coming soon..."

# Documentation (future expansion)
docs:
	@echo "📖 Documentation generation coming soon..."
