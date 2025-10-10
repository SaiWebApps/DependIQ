"""Tests for GitHub OAuth authentication flow"""

import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import PageHelpers


class TestGitHubOAuth:
    """Test GitHub OAuth authentication flow"""

    def test_github_oauth_button_present(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that GitHub OAuth button is present and functional"""
        driver.get(f"{base_url}/login")
        PageHelpers.wait_for_element(wait, By.ID, "email")

        github_btn = driver.find_element(By.CLASS_NAME, "github-btn")
        assert github_btn.is_displayed(), "GitHub OAuth button should be visible"
        assert (
            "github" in github_btn.text.lower()
        ), "GitHub button should mention GitHub"

        print("✓ GitHub OAuth button is present and visible")

    def test_github_oauth_redirect(
        self, driver: webdriver.Chrome, wait: WebDriverWait, base_url: str
    ):
        """Test that clicking GitHub button initiates OAuth flow"""
        driver.get(f"{base_url}/login")

        github_btn = PageHelpers.wait_for_clickable(wait, By.CLASS_NAME, "github-btn")
        original_url = driver.current_url
        github_btn.click()

        time.sleep(2)
        new_url = driver.current_url

        assert new_url != original_url, "Should redirect after clicking GitHub button"

        if "github.com" in new_url:
            assert (
                "authorize" in new_url or "login" in new_url
            ), "Should redirect to GitHub authorization page"
            print("✓ GitHub OAuth redirect to GitHub.com initiated")
        elif "auth/github" in new_url:
            print("✓ GitHub OAuth endpoint called")
        else:
            print(f"⚠ Redirected to: {new_url}")

    def test_github_register_button_present(
        self, driver: webdriver.Chrome, base_url: str
    ):
        """Test that GitHub button is also present on register page"""
        driver.get(f"{base_url}/register")

        github_btn = driver.find_element(By.CLASS_NAME, "github-btn")
        assert (
            github_btn.is_displayed()
        ), "GitHub OAuth button should be visible on register page"

        print("✓ GitHub OAuth available on register page")
