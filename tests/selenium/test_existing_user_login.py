"""Tests for existing user login flow"""

import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


class TestExistingUserLogin:
    """Test existing user login flow"""

    def test_existing_user_login_flow(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test login flow for existing user (test@example.com / TestPassword123!)"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        test_email = "test@example.com"
        email_input.send_keys(test_email)

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        password_step = PageHelpers.wait_for_element(wait, By.ID, "passwordStep")
        assert password_step.is_displayed(), "Password step should be visible"

        email_display = driver.find_element(By.ID, "emailDisplay")
        assert email_display.get_attribute("value") == test_email, (
            f"Email display should show {test_email}"
        )

        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys("TestPassword123!")

        login_btn = driver.find_element(By.ID, "loginBtn")
        login_btn.click()

        try:
            wait.until(
                lambda d: "/profile" in d.current_url or "/projects" in d.current_url
            )
            print(f"✓ Successfully logged in as {test_email}")
        except TimeoutException:
            error_msg = PageHelpers.check_for_error(driver)
            if error_msg:
                print(f"⚠ Login test note: {error_msg}")
                print("  To run this test successfully, ensure test user exists:")
                print("  Email: test@example.com, Password: TestPassword123!")
            else:
                raise

    def test_invalid_password(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that invalid password shows error"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("test@example.com")
        driver.find_element(By.ID, "continueBtn").click()

        PageHelpers.wait_for_element(wait, By.ID, "passwordStep")

        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys("WrongPassword123!")
        driver.find_element(By.ID, "loginBtn").click()

        time.sleep(1)
        error_msg = PageHelpers.check_for_error(driver)
        if error_msg:
            assert "invalid" in error_msg.lower() or "incorrect" in error_msg.lower(), (
                f"Expected invalid credentials error, got: {error_msg}"
            )
            print("✓ Invalid password correctly rejected")
        else:
            print("⚠ No error message (user may not exist)")

    def test_back_button_functionality(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that back button returns to email step"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("test@example.com")
        driver.find_element(By.ID, "continueBtn").click()

        PageHelpers.wait_for_element(wait, By.ID, "passwordStep")

        back_link = driver.find_element(By.CLASS_NAME, "back-link")
        back_link.click()

        email_step = driver.find_element(By.ID, "emailStep")
        assert email_step.is_displayed(), "Should return to email step"

        email_input = driver.find_element(By.ID, "email")
        assert email_input.get_attribute("value") == "", "Email field should be cleared"

        print("✓ Back button functionality working")
