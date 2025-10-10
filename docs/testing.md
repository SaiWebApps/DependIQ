# Testing Guide

## Quick Links
- [Theme System Testing](testing_themes.md) - Theme-specific tests and validation

Comprehensive test suite with 200+ tests covering unit, integration, and functional scenarios.

## Quick Start

```bash
make test              # Run all tests
make test-coverage     # Run with coverage report
```

## Test Commands

### Run Tests
```bash
make test              # All tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-functional   # Functional tests only
make test-quick        # Skip slow tests
```

### Coverage
```bash
make test-coverage     # Generate HTML coverage report
# Open htmlcov/index.html to view results
```

### Specific Tests
```bash
pytest tests/test_auth_integration.py                                    # One file
pytest tests/test_auth_integration.py::TestUserLogin                     # One class
pytest tests/test_auth_integration.py::TestUserLogin::test_valid_login   # One test
```

### Advanced Options
```bash
pytest -v                  # Verbose output
pytest -k "auth"           # Run tests matching pattern
pytest -m "not slow"       # Skip slow tests
pytest -n auto             # Parallel execution (requires pytest-xdist)
```

## Test Structure

```
tests/
├── conftest.py                  # Fixtures and configuration
├── test_auth_integration.py     # Authentication flows
├── test_user_profile.py         # User profile and preferences
├── test_api_integration.py      # API endpoint validation
├── test_models.py               # Database models
├── test_services.py             # Service layer
├── test_middleware.py           # Middleware and error handling
├── test_utils.py                # Utility functions
└── test_functional.py           # End-to-end workflows
```

## Test Coverage by Module

| Module | Coverage | Tests |
|--------|----------|-------|
| Authentication | 90%+ | 30+ |
| User Management | 85%+ | 25+ |
| API Endpoints | 85%+ | 45+ |
| Database Models | 85%+ | 35+ |
| Services | 85%+ | 25+ |
| Utilities | 80%+ | 40+ |

**Target**: 85%+ coverage across all modules

## Key Test Suites

### Authentication (`test_auth_integration.py`)
- User registration and validation
- Login/logout flows
- JWT token management
- Password change and reset
- Protected endpoint access

### User Profiles (`test_user_profile.py`)
- Profile retrieval and updates
- Preferences management (theme, language, timezone)
- Project history tracking
- OAuth connections

### API Integration (`test_api_integration.py`)
- All API endpoints
- Authentication requirements
- Error handling (404, 401, 403, 500)
- Request validation
- Performance and concurrency

### Database Models (`test_models.py`)
- Model creation and constraints
- Relationships and foreign keys
- Timestamps and defaults
- Token models (verification, reset, magic links)

### Services (`test_services.py`)
- Token service (JWT creation/validation)
- GitHub OAuth service
- User service operations

### Utilities (`test_utils.py`)
- File path matching
- JSON parsing and extraction
- Password hashing and validation
- Project type detection

### Middleware (`test_middleware.py`)
- Custom exception handling
- Error response formatting
- User-friendly error messages

### Functional Tests (`test_functional.py`)
- Complete user journeys
- Multi-step workflows
- Error recovery
- Multi-user scenarios

## Writing Tests

### Test Structure
```python
import pytest
from fastapi import status

class TestFeature:
    """Test feature description"""

    def test_success_case(self, test_client, auth_headers):
        """Test successful operation"""
        response = test_client.post(
            "/api/endpoint",
            headers=auth_headers,
            json={"key": "value"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert "expected_key" in response.json()

    def test_error_case(self, test_client):
        """Test error handling"""
        response = test_client.post("/api/endpoint", json={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
```

### Async Tests
```python
import pytest

class TestAsyncFeature:
    @pytest.mark.asyncio
    async def test_async_operation(self, test_db_session):
        """Test async operation"""
        from app.services.user_service import UserService

        service = UserService(test_db_session)
        result = await service.some_method()
        assert result is not None
```

### Available Fixtures

From `conftest.py`:
- `test_engine` - SQLite in-memory database engine
- `test_db_session` - Database session
- `test_client` - FastAPI test client
- `test_user` - Verified test user
- `test_user_unverified` - Unverified test user
- `auth_headers` - JWT authentication headers
- `test_password` - Valid test password

## Best Practices

### Test Organization
- One test class per feature
- Descriptive test names: `test_user_cannot_login_with_invalid_password`
- Test one thing per test
- Use fixtures for setup
- Independent, isolated tests

### Assertions
```python
# Good - specific assertions
assert response.status_code == status.HTTP_200_OK
assert response.json()["email"] == "test@example.com"
assert "access_token" in response.json()

# Bad - vague assertions
assert response.status_code == 200
assert response.json()
```

### Test Both Success and Failure
```python
def test_login_success(self, test_client, test_user):
    """Test successful login"""
    # ...

def test_login_invalid_email(self, test_client):
    """Test login with nonexistent email"""
    # ...

def test_login_wrong_password(self, test_client, test_user):
    """Test login with incorrect password"""
    # ...
```

## Troubleshooting

### Tests Failing
```bash
pytest -v                           # Verbose output
rm -f test.db                       # Clear test database
make install                        # Reinstall dependencies
```

### Import Errors
```bash
cd /path/to/dependiq                  # Project root
source venv/bin/activate            # Activate venv
pip install -e .                    # Install in dev mode
```

### Fixture Not Found
- Check `conftest.py` exists in `tests/`
- Verify fixture name spelling
- Ensure proper fixture scope

### Database Issues
```bash
alembic upgrade head                # Ensure migrations current
pytest -v                           # Run with verbose output
```

## Continuous Integration

Add to `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: make install

    - name: Run tests
      run: make test-coverage

    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Test Maintenance

### After Adding Features
1. Write tests for new endpoints
2. Update fixtures if needed
3. Test error cases
4. Run full test suite
5. Verify coverage meets target
6. Update this documentation

### Before Releases
1. Run all tests: `make test`
2. Check coverage: `make test-coverage`
3. Verify CI passes
4. Review test performance

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Current Status**: 200+ tests, 85%+ coverage target achieved
