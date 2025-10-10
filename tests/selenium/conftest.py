"""Shared fixtures and configuration for Selenium tests"""

import os
from collections.abc import Generator

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT = 10


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
