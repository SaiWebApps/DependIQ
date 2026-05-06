"""Shared fixtures and configuration for Selenium tests"""

import asyncio
import os
from collections.abc import Generator

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.models import User

from .email_capture import EmailCaptureService

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT = 10


# Database setup for test cleanup
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_engine(event_loop):
    """Create database engine for test cleanup"""
    engine = create_async_engine(Config.DATABASE_URL, echo=False)
    yield engine
    # Clean up engine at the end of the session using the same event loop
    event_loop.run_until_complete(engine.dispose())


@pytest.fixture(scope="session")
def db_session_factory(db_engine):
    """Create session factory for database operations"""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    return async_session


@pytest.fixture
async def email_service():
    """Create email capture service for tests"""
    service = EmailCaptureService()
    # Only return service if mail.tm is being used (which doesn't require API keys)
    # Resend/Mailosaur/Mailtrap require verified domains or specific configurations
    if service.service == "mailtm":
        return service
    # If using other services, check if they're properly configured for test emails
    return service


@pytest.fixture
def test_email_generator(email_service, event_loop):
    """Generate test email addresses"""

    def _generate(base_name: str = "test") -> str:
        if email_service.is_configured():
            # Use the existing event loop instead of creating a new one
            return event_loop.run_until_complete(
                email_service.get_test_email(base_name)
            )
        # Fallback for local testing without email service
        import uuid

        return f"{base_name}_{uuid.uuid4().hex[:8]}@example.com"

    return _generate


@pytest.fixture
def cleanup_test_users(db_session_factory, event_loop):
    """Cleanup fixture to delete test users after tests"""
    created_emails = []

    def register_email(email: str):
        """Register an email for cleanup"""
        created_emails.append(email)

    yield register_email

    # Cleanup after test using the existing event loop
    if created_emails:

        async def cleanup():
            async with db_session_factory() as session:
                for email in created_emails:
                    result = await session.execute(
                        select(User).where(User.email == email.lower())
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        await session.delete(user)
                await session.commit()

        event_loop.run_until_complete(cleanup())


@pytest.fixture(scope="function")
def driver() -> Generator[webdriver.Chrome, None, None]:
    """Create a Chrome WebDriver instance

    Uses Selenium 4's built-in driver manager which automatically:
    - Downloads Chrome for Testing if Chrome isn't installed
    - Manages ChromeDriver versions
    - Works in headless mode without requiring Chrome installation
    """
    chrome_options = Options()

    if HEADLESS:
        chrome_options.add_argument("--headless=new")  # New headless mode
        chrome_options.add_argument("--disable-gpu")

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    # Selenium 4.6+ uses built-in Selenium Manager - no need for webdriver-manager
    # It will automatically download Chrome for Testing and ChromeDriver
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(5)

    yield driver

    driver.quit()


@pytest.fixture(scope="function")
def wait(driver: webdriver.Chrome) -> WebDriverWait:
    """Create a WebDriverWait instance"""
    return WebDriverWait(driver, TIMEOUT)


@pytest.fixture
def base_url() -> str:
    """Get base URL for tests"""
    return BASE_URL
