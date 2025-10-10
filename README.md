# dependiq - AI-Powered Dependency Management

Automatically analyze, research, and update dependencies in your projects using AI.

## Features

- 🎨 **7 Beautiful Themes** - Light, Dark, Ocean, Forest, Nord, Dracula, and System Auto themes
- ♿ **Accessibility Features** - High contrast, colorblind modes, font sizes, reduce motion
- Automatic project detection (Python, Java/Scala)
- AI-powered dependency analysis and version research
- Automated dependency updates with validation
- GitHub integration for direct repository access
- User authentication with JWT and OAuth (GitHub)
- Project history tracking and preferences management

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 14+
- OpenAI API key

### Setup

```bash
# Install dependencies
make install

# Setup database
make db-setup

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY, DATABASE_URL, JWT_SECRET_KEY

# Start application
make run
```

Access the application at http://localhost:8000

### Complete First-Time Setup

```bash
# One command to set up everything
make setup
```

This installs dependencies, configures the database, formats code, and installs pre-commit hooks.

## Usage

### Web Interface

1. Register/login at http://localhost:8000
2. Upload project ZIP or connect GitHub repository
3. Review AI-generated dependency updates
4. Download updated project

### API

Full API documentation available at http://localhost:8000/docs when the server is running.

Example authentication flow:
```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!","confirm_password":"SecurePass123!"}'

# Login and get token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!"}'
```

## Supported Projects

- **Python**: `requirements.txt`, `pyproject.toml`
- **Java**: `pom.xml` (Maven), `build.gradle` (Gradle)
- **Scala**: `build.sbt` (SBT)

## Configuration

### Required Environment Variables
```bash
OPENAI_API_KEY=sk-...                                    # OpenAI API key
DATABASE_URL=postgresql+asyncpg://localhost/dependiq      # Database URL
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### Optional Configuration
```bash
# GitHub OAuth
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# Email (SendGrid recommended)
EMAIL_SERVICE=sendgrid
SENDGRID_API_KEY=your_api_key
EMAIL_FROM=noreply@yourdomain.com

# Security (production only)
SECURE_COOKIES=true
```

Setup GitHub OAuth with: `make github`

## Development

### Testing
```bash
make test              # Run all tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-coverage     # With coverage report
```

See [`docs/TESTING.md`](docs/TESTING.md) for comprehensive testing documentation.

### Code Quality
```bash
make format     # Format with black, isort, ruff
make lint       # Run linter
make typecheck  # Type checking
make quality    # Run all checks
```

### Database Management
```bash
make db-status   # Check database status
make db-migrate  # Apply migrations
make db-reset    # Reset database (⚠️ deletes data)
```

See [`docs/DATABASE.md`](docs/DATABASE.md) for detailed database documentation.

## Common Tasks

```bash
make help        # Show all available commands
make setup       # Complete project setup
make run         # Start the application
make quality     # Run all code quality checks
make clean       # Clean up generated files
```

## Troubleshooting

**Database issues**: Run `make db-status` to diagnose and `make db-reset` to reset (⚠️ deletes data)

**Dependency issues**: Run `make install` to reinstall dependencies

**Test failures**: See [`docs/TESTING.md`](docs/TESTING.md) for debugging steps

## Documentation

- [`docs/DATABASE.md`](docs/DATABASE.md) - Database setup and management
- [`docs/TESTING.md`](docs/TESTING.md) - Testing guide and coverage
- [`docs/themes.md`](docs/themes.md) - Theme customization guide
- [`docs/accessibility.md`](docs/accessibility.md) - Accessibility features guide
- [`docs/testing_themes.md`](docs/testing_themes.md) - Theme testing guide
- [`docs/design/`](docs/design/) - Architecture documentation
- API docs: http://localhost:8000/docs (when running)

## Project Structure

```
dependiq/
├── app/
│   ├── api/          # API endpoints
│   ├── middleware/   # Auth & error handling
│   ├── models/       # Database models
│   ├── services/     # Business logic
│   └── utils/        # Utilities
├── alembic/          # Database migrations
├── prompts/          # AI prompts
├── static/           # Frontend assets
├── templates/        # HTML templates
├── tests/            # Test suite
└── Makefile          # Development commands
```

---

Built with FastAPI, OpenAI, and PostgreSQL
