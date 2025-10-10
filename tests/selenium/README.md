# Selenium Tests

End-to-end authentication tests organized by functionality.

## Structure

```
tests/selenium/
├── conftest.py                      # Shared fixtures (driver, wait)
├── helpers.py                       # Page interaction utilities
├── test_new_user_registration.py   # New user magic link flow
├── test_existing_user_login.py     # Login with email/password
├── test_github_oauth.py             # GitHub OAuth flow
├── test_ui_elements.py              # UI interactions
└── test_smoke.py                    # Basic accessibility checks
```

## Quick Start

```bash
# Terminal 1: Start application
make run

# Terminal 2: Run tests
make test-selenium              # With visible browser
make test-selenium-headless     # Headless mode (for CI/CD)
```

## Configuration

Environment variables:

- `TEST_BASE_URL` - Application URL (default: `http://localhost:8000`)
- `HEADLESS` - Run headless (default: `false`)

## Deployment Testing

```bash
# Staging
TEST_BASE_URL=https://staging.app.com HEADLESS=true make test-selenium

# Production smoke test
TEST_BASE_URL=https://app.com HEADLESS=true pytest tests/selenium/test_smoke.py -v
