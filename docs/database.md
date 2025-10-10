# Database Management

Quick reference for database operations in dependiq.

## Quick Start

```bash
make db-setup    # Complete setup: start PostgreSQL, create DB, run migrations
```

## Commands

### Status & Diagnostics
```bash
make db-status   # Show PostgreSQL status, databases, tables, and migrations
```

### Service Management
```bash
make db-start    # Start PostgreSQL service
make db-stop     # Stop PostgreSQL service
```

### Database Operations
```bash
make db-create   # Create dependiq database
make db-migrate  # Apply pending migrations
make db-reset    # Drop and recreate database (⚠️ DELETES ALL DATA)
```

## Manual Operations

### Database Connection
```bash
psql -d dependiq              # Connect to database
psql -l                     # List all databases
psql -d dependiq -c "\dt"     # List tables
psql -d dependiq -c "\d users" # Describe table
```

### Migrations
```bash
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one migration
alembic current                                   # Show current version
```

## Configuration

### Environment Variable
```bash
DATABASE_URL=postgresql+asyncpg://localhost/dependiq
```

With credentials:
```bash
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/dependiq
```

## Database Schema

Core tables:
- `users` - User accounts and authentication
- `user_sessions` - Active sessions
- `user_preferences` - User settings (theme, language, timezone)
- `email_verification_tokens` - Email verification
- `password_reset_tokens` - Password reset flow
- `magic_link_tokens` - Registration links
- `oauth_connections` - GitHub OAuth connections
- `project_history` - Project upload history

## Installation

### macOS
```bash
brew install postgresql@14
brew services start postgresql@14
```

### Linux (Ubuntu/Debian)
```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Docker
```bash
docker run --name dependiq-postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=dependiq \
  -p 5432:5432 -d postgres:15
```

Update `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dependiq
```

## Troubleshooting

### Connection Refused
```bash
make db-start    # Start PostgreSQL
make db-status   # Verify it's running
```

### Database Doesn't Exist
```bash
make db-create
```

### Tables Not Created
```bash
make db-migrate
```

### Complete Reset
```bash
make db-reset    # ⚠️ Deletes all data
```

### Manual Reset
```bash
dropdb dependiq
createdb dependiq
alembic upgrade head
```
