"""Helper utilities for Selenium tests"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


class PageHelpers:
    """Helper methods for interacting with pages"""

    @staticmethod
    def wait_for_element(wait: WebDriverWait, by: By, value: str):
        """Wait for element to be present and visible"""
        return wait.until(
            expected_conditions.visibility_of_element_located((by, value))
        )

    @staticmethod
    def wait_for_clickable(wait: WebDriverWait, by: By, value: str):
        """Wait for element to be clickable"""
        return wait.until(expected_conditions.element_to_be_clickable((by, value)))

    @staticmethod
    def check_for_error(driver: webdriver.Chrome) -> str | None:
        """Check if an error message is displayed"""
        try:
            error_element = driver.find_element(By.ID, "errorMessage")
            if error_element.is_displayed():
                return error_element.text
        except:
            pass
        return None

    @staticmethod
    def check_for_success(driver: webdriver.Chrome) -> str | None:
        """Check if a success message is displayed"""
        try:
            success_element = driver.find_element(By.ID, "successMessage")
            if success_element.is_displayed():
                return success_element.text
        except:
            pass
        return None
