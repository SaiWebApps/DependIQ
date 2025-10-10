"""Smoke tests to verify application is accessible"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


def test_application_running(driver: webdriver.Chrome, base_url: str):
    """Verify the application is accessible"""
    driver.get(base_url)
    assert driver.title, "Application should be accessible"
    print(f"✓ Application is running at {base_url}")


def test_login_page_loads(driver: webdriver.Chrome, wait: WebDriverWait, base_url: str):
    """Verify login page loads correctly"""
    driver.get(f"{base_url}/login")

    assert "DependIQ" in driver.title, "Page title should contain DependIQ"

    logo = driver.find_element(By.CSS_SELECTOR, "img[alt='DependIQ Logo']")
    assert logo.is_displayed(), "Logo should be visible"

    email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
    assert email_input.is_displayed(), "Email input should be visible"

    print("✓ Login page loads correctly")
