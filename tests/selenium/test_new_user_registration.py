"""Tests for new user account creation via magic link flow"""

import uuid

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


class TestNewUserAccountCreation:
    """Test new user account creation via magic link flow"""

    def test_new_user_magic_link_flow(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test complete new user registration flow using magic link"""
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"

        driver.get(f"{base_url}/login")
        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys(test_email)

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        # Wait for success message element to become visible (async operation)
        success_element = wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "successMessage"))
        )
        success_msg = success_element.text

        assert (
            "registration link sent" in success_msg.lower()
        ), f"Expected registration link message, got: {success_msg}"

        print(f"✓ New user magic link flow initiated for {test_email}")

    def test_new_user_registration_form_validation(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that the registration form properly validates email format"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("not-an-email")

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        assert driver.find_element(
            By.ID, "emailStep"
        ).is_displayed(), "Should remain on email step with invalid email"

        print("✓ Email validation working correctly")
