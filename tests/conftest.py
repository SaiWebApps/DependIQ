"""
Pytest configuration and fixtures for testing
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User
from main import app


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Treat skipped tests as failures. No test should be skipped."""
    outcome = yield
    report = outcome.get_result()
    if report.skipped:
        report.outcome = "failed"
        report.longrepr = (
            f"FAILED: {item.nodeid} was skipped. "
            "Skipped tests are treated as failures. Remove the skip marker and fix the test."
        )

# Test-only identifiers loaded from environment with fallback for CI
TEST_WORKOS_USER_ID = os.getenv("TEST_WORKOS_USER_ID", "user_test_ci_001")
TEST_GITHUB_WORKOS_USER_ID = os.getenv(
    "TEST_GITHUB_WORKOS_USER_ID", "user_github_ci_001"
)
TEST_UNVERIFIED_WORKOS_USER_ID = os.getenv(
    "TEST_UNVERIFIED_WORKOS_USER_ID", "user_unverified_ci_001"
)
TEST_GITHUB_TOKEN = os.getenv("TEST_GITHUB_TOKEN", "ghp_test_token_for_ci")
TEST_SESSION_TOKEN = os.getenv("TEST_SESSION_TOKEN", "session_token_for_ci")


# Test database URL - use unique shared in-memory SQLite per test function
def get_test_db_url():
    import uuid

    return f"sqlite+aiosqlite:///file:testdb_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine with fresh tables for each test"""
    # Create unique database URL for this test
    test_db_url = get_test_db_url()

    engine = create_async_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session"""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture(scope="function")
def test_client(test_engine, test_db_session):
    """Create a test client with database dependency override"""

    # Override the get_db dependency
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(test_db_session: AsyncSession) -> User:
    """Create a test user with WorkOS-style auth"""
    user = User(
        email="test@example.com",
        workos_user_id=TEST_WORKOS_USER_ID,
        email_verified=True,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_with_github(test_db_session: AsyncSession) -> User:
    """Create a test user with GitHub token"""
    user = User(
        email="github@example.com",
        workos_user_id=TEST_GITHUB_WORKOS_USER_ID,
        email_verified=True,
        is_active=True,
        github_access_token=TEST_GITHUB_TOKEN,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_unverified(test_db_session: AsyncSession) -> User:
    """Create an unverified test user"""
    user = User(
        email="unverified@example.com",
        workos_user_id=TEST_UNVERIFIED_WORKOS_USER_ID,
        email_verified=False,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
def auth_cookie(test_user):
    """Get a mock session cookie value for the test user.

    In tests, we mock verify_session to accept this token.
    """
    return TEST_SESSION_TOKEN


@pytest.fixture
def auth_headers(test_user, _mock_verify_session):
    """Provide auth via cookie header for tests that use auth_headers pattern.

    The middleware now reads from cookies, so we pass the cookie header.
    The _mock_verify_session fixture patches verify_session globally.
    """
    return {"cookie": f"diq_session={TEST_SESSION_TOKEN}"}


@pytest.fixture
def _mock_verify_session(test_user):
    """Patch verify_or_refresh_session to return a successful result."""
    from unittest.mock import patch

    from workos.session import AuthenticateWithSessionCookieSuccessResponse

    mock_result = AuthenticateWithSessionCookieSuccessResponse(
        authenticated=True,
        session_id="sess_test_ci_001",
        user={"id": TEST_WORKOS_USER_ID, "email": "test@example.com"},
    )

    with patch("app.services.workos_auth.verify_or_refresh_session") as mock_v:
        mock_v.return_value = (mock_result, None)
        yield mock_v
