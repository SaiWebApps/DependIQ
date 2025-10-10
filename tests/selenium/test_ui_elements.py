"""Tests for UI elements and interactions"""

import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


class TestUIElements:
    """Test various UI elements and interactions"""

    def test_password_visibility_toggle(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test password visibility toggle button"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("test@example.com")
        driver.find_element(By.ID, "continueBtn").click()

        PageHelpers.wait_for_element(wait, By.ID, "passwordStep")

        password_input = driver.find_element(By.ID, "password")
        toggle_btn = driver.find_element(By.CLASS_NAME, "password-toggle")

        assert (
            password_input.get_attribute("type") == "password"
        ), "Password field should start as password type"

        toggle_btn.click()
        time.sleep(0.5)
        assert (
            password_input.get_attribute("type") == "text"
        ), "Password field should change to text type"

        toggle_btn.click()
        time.sleep(0.5)
        assert (
            password_input.get_attribute("type") == "password"
        ), "Password field should return to password type"

        print("✓ Password visibility toggle working")

    def test_forgot_password_link(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test forgot password link navigation"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("test@example.com")
        driver.find_element(By.ID, "continueBtn").click()

        PageHelpers.wait_for_element(wait, By.ID, "passwordStep")

        forgot_link = driver.find_element(By.LINK_TEXT, "Forgot password?")
        forgot_link.click()

        wait.until(lambda d: "/forgot-password" in d.current_url)
        assert (
            "/forgot-password" in driver.current_url
        ), "Should navigate to forgot password page"

        print("✓ Forgot password link working")
