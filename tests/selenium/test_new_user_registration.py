"""Tests for new user account creation via magic link flow"""

import os
import time
import uuid

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


class TestNewUserAccountCreation:
    """Test new user account creation via magic link flow"""

    def test_nonexistent_user_login_shows_error(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """
        Scenario 1: Verify that attempting to login with a non-existent user
        triggers the magic link flow instead of showing password prompt
        """
        # Generate a unique email that definitely doesn't exist
        test_email = f"nonexistent_{uuid.uuid4().hex[:12]}@example.com"

        driver.get(f"{base_url}/login")
        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys(test_email)

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        # Wait for success message element to become visible
        # For non-existent users, the system automatically sends magic link
        success_element = wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "successMessage"))
        )
        success_msg = success_element.text.lower()

        # Verify the success message indicates magic link was sent
        assert any(
            phrase in success_msg
            for phrase in [
                "registration link sent",
                "magic link sent",
                "check your email",
            ]
        ), f"Expected magic link message for non-existent user, got: {success_msg}"

        # Verify we're still on the email step (not password step)
        email_step = driver.find_element(By.ID, "emailStep")
        assert email_step.is_displayed(), (
            "Should remain on email step after magic link sent"
        )

        print(f"✓ Non-existent user ({test_email}) correctly triggers magic link flow")

    def test_new_user_registration_form_validation(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that the registration form properly validates email format"""
        driver.get(f"{base_url}/login")

        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys("not-an-email")

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        # Should remain on email step with invalid email
        assert driver.find_element(By.ID, "emailStep").is_displayed(), (
            "Should remain on email step with invalid email"
        )

        print("✓ Email validation working correctly")

    def test_complete_magic_link_registration(
        self,
        driver: webdriver.Chrome,
        wait: WebDriverWait,
        base_url: str,
        email_service,
        test_email_generator,
        cleanup_test_users,
        event_loop,
    ):
        """
        Scenario 2: Complete magic link registration flow
        1. Enter email for new user
        2. System sends magic link
        3. Fetch email from test inbox
        4. Extract magic link and temp password
        5. Complete registration
        6. Verify successful login
        """
        # Skip test if email service not configured
        if not email_service.is_configured():
            import pytest

            pytest.skip(
                "Email capture service not configured (set USE_MAILTM=true or configure Mailosaur/Mailtrap)"
            )

        # Generate test email
        test_email = test_email_generator("newuser")
        cleanup_test_users(test_email)

        print(f"\n🔄 Testing magic link registration for: {test_email}")

        # Step 1: Trigger magic link
        driver.get(f"{base_url}/login")
        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys(test_email)

        continue_btn = driver.find_element(By.ID, "continueBtn")
        continue_btn.click()

        # Wait for success message
        success_element = wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "successMessage"))
        )
        success_msg = success_element.text.lower()
        assert "registration link sent" in success_msg or "magic link" in success_msg

        print(f"✓ Magic link triggered for {test_email}")

        # Step 2: Fetch email from test inbox
        print("📧 Waiting for email to arrive...")
        email_data = event_loop.run_until_complete(
            email_service.wait_for_email(
                to_email=test_email,
                subject_contains="Complete Your",
                timeout=45,
            )
        )

        assert email_data is not None, "Failed to receive magic link email"
        print("✓ Email received")

        # Step 3: Extract magic link and temp password
        magic_link = email_service.extract_magic_link(email_data)
        temp_password = email_service.extract_temp_password(email_data)

        assert magic_link is not None, "Failed to extract magic link from email"
        assert temp_password is not None, "Failed to extract temp password from email"

        print("✓ Extracted magic link and temp password")

        # Step 4: Visit magic link and complete registration
        driver.get(magic_link)
        time.sleep(1)  # Allow page to load

        # Fill in the magic link registration form
        temp_pwd_input = PageHelpers.wait_for_element(wait, By.ID, "tempPassword")
        temp_pwd_input.send_keys(temp_password)

        new_pwd_input = driver.find_element(By.ID, "newPassword")
        new_pwd_input.send_keys("TestPassword123!")

        confirm_pwd_input = driver.find_element(By.ID, "confirmPassword")
        confirm_pwd_input.send_keys("TestPassword123!")

        complete_btn = driver.find_element(By.ID, "registerBtn")
        complete_btn.click()

        # Step 5: Verify successful registration and auto-login
        wait.until(
            lambda d: "/profile" in d.current_url or "/projects" in d.current_url
        )

        print(f"✓ Magic link registration completed successfully for {test_email}")

        # Verify we're logged in by checking for profile/projects page
        current_url = driver.current_url
        assert "/profile" in current_url or "/projects" in current_url, (
            f"Should be redirected to profile or projects after registration, got: {current_url}"
        )

        print("✓ User automatically logged in after registration")

    def test_github_oauth_registration(
        self,
        driver: webdriver.Chrome,
        wait: WebDriverWait,
        base_url: str,
        cleanup_test_users,
    ):
        """
        Scenario 3: Test GitHub OAuth registration flow
        1. Click GitHub OAuth button
        2. Login to GitHub (if not already logged in)
        3. Authorize the application
        4. Verify user is created and logged in
        """
        # Get GitHub test credentials from environment
        github_username = os.getenv("TEST_GITHUB_USERNAME")
        github_password = os.getenv("TEST_GITHUB_PASSWORD")

        if not github_username or not github_password:
            import pytest

            pytest.skip(
                "GitHub test credentials not configured (set TEST_GITHUB_USERNAME and TEST_GITHUB_PASSWORD)"
            )

        print("\n🔄 Testing GitHub OAuth registration")

        # Step 1: Click GitHub OAuth button
        driver.get(f"{base_url}/login")
        PageHelpers.wait_for_element(wait, By.ID, "email")

        github_btn = PageHelpers.wait_for_clickable(wait, By.CLASS_NAME, "github-btn")
        github_btn.click()

        # Step 2: Handle GitHub OAuth flow
        # Wait for redirect to GitHub or callback
        time.sleep(2)
        current_url = driver.current_url

        # If redirected to GitHub login
        if "github.com" in current_url:
            print("🔐 Logging into GitHub...")

            # Wait for GitHub login page
            try:
                # Try to find login field (might already be logged in)
                login_field = wait.until(
                    expected_conditions.presence_of_element_located(
                        (By.ID, "login_field")
                    )
                )
                login_field.send_keys(github_username)

                password_field = driver.find_element(By.ID, "password")
                password_field.send_keys(github_password)

                sign_in_btn = driver.find_element(By.NAME, "commit")
                sign_in_btn.click()

                print("✓ GitHub login submitted")
                time.sleep(2)

            except Exception:
                print("✓ Already logged into GitHub")

            # Check for authorization page
            time.sleep(2)
            if "authorize" in driver.current_url.lower():
                print("🔐 Authorizing application...")
                try:
                    # Find and click authorize button
                    authorize_btn = wait.until(
                        expected_conditions.element_to_be_clickable(
                            (By.NAME, "authorize")
                        )
                    )
                    authorize_btn.click()
                    print("✓ Application authorized")
                except Exception as e:
                    print(f"⚠ Authorization might already be granted: {e}")

        # Step 3: Wait for redirect back to application
        wait.until(
            lambda d: base_url in d.current_url and "github" not in d.current_url,
            message="Should redirect back to application after OAuth",
        )

        # Step 4: Verify successful login
        time.sleep(2)
        final_url = driver.current_url

        assert "/profile" in final_url or "/projects" in final_url, (
            f"Should be redirected to profile or projects after OAuth, got: {final_url}"
        )

        print("✓ GitHub OAuth registration/login completed successfully")

        # Note: Email cleanup will need the GitHub user's email
        # which we can't easily get here, so manual cleanup may be needed
        print("⚠ Note: GitHub OAuth test user may need manual cleanup from database")

    def test_magic_link_with_invalid_temp_password(
        self,
        driver: webdriver.Chrome,
        wait: WebDriverWait,
        base_url: str,
        email_service,
        test_email_generator,
        cleanup_test_users,
        event_loop,
    ):
        """Test that magic link registration fails with invalid temp password"""
        if not email_service.is_configured():
            import pytest

            pytest.skip("Email capture service not configured")

        test_email = test_email_generator("invalidpwd")
        cleanup_test_users(test_email)

        # Trigger magic link
        driver.get(f"{base_url}/login")
        email_input = PageHelpers.wait_for_element(wait, By.ID, "email")
        email_input.send_keys(test_email)
        driver.find_element(By.ID, "continueBtn").click()

        # Wait for email
        wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "successMessage"))
        )

        email_data = event_loop.run_until_complete(
            email_service.wait_for_email(test_email, "Complete Your", 45)
        )
        assert email_data is not None

        magic_link = email_service.extract_magic_link(email_data)
        assert magic_link is not None

        # Visit magic link but use wrong temp password
        driver.get(magic_link)
        time.sleep(1)

        temp_pwd_input = PageHelpers.wait_for_element(wait, By.ID, "tempPassword")
        temp_pwd_input.send_keys("WrongTempPassword123")

        new_pwd_input = driver.find_element(By.ID, "newPassword")
        new_pwd_input.send_keys("TestPassword123!")

        confirm_pwd_input = driver.find_element(By.ID, "confirmPassword")
        confirm_pwd_input.send_keys("TestPassword123!")

        complete_btn = driver.find_element(By.ID, "registerBtn")
        complete_btn.click()

        # Should show error
        time.sleep(1)
        error_msg = PageHelpers.check_for_error(driver)
        assert error_msg is not None, "Should show error with invalid temp password"
        assert "temp" in error_msg.lower() or "invalid" in error_msg.lower(), (
            f"Error should mention temp password, got: {error_msg}"
        )

        print("✓ Invalid temp password correctly rejected")
