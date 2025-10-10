"""
Pytest configuration and fixtures for testing
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User
from app.utils.password_utils import hash_password
from main import app


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
    """Create a test user"""
    user = User(
        email="test@example.com",
        password_hash=hash_password("TestPassword123!"),
        email_verified=True,
        is_active=True,
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
        password_hash=hash_password("TestPassword123!"),
        email_verified=False,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_client, test_user):
    """Get authentication headers for test user"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def test_password():
    """Test password that meets all requirements"""
    return "TestPassword123!"


@pytest.fixture
def weak_password():
    """Weak password for testing validation"""
    return "weak"


@pytest.fixture
def valid_user_data():
    """Valid user registration data"""
    return {
        "email": "newuser@example.com",
        "password": "ValidPass123!",
        "confirm_password": "ValidPass123!",
    }


@pytest.fixture
def invalid_user_data():
    """Invalid user registration data (mismatched passwords)"""
    return {
        "email": "newuser@example.com",
        "password": "ValidPass123!",
        "confirm_password": "DifferentPass123!",
    }
