"""Email capture utility for testing email flows

Supports Mailosaur, Mailtrap, and mail.tm (free) for retrieving test emails.
"""

import asyncio
import os
import re
import time

import httpx


class EmailCaptureService:
    """Service to capture and retrieve emails from test inbox"""

    def __init__(self):
        """Initialize email capture service based on environment configuration"""
        # Mailosaur configuration
        self.mailosaur_api_key = os.getenv("MAILOSAUR_API_KEY")
        self.mailosaur_server_id = os.getenv("MAILOSAUR_SERVER_ID")

        # Mailtrap configuration
        self.mailtrap_api_token = os.getenv("MAILTRAP_API_TOKEN")
        self.mailtrap_inbox_id = os.getenv("MAILTRAP_INBOX_ID")

        # mail.tm configuration (free service - no API key needed!)
        self.use_mailtm = os.getenv("USE_MAILTM", "true").lower() == "true"

        # Test email domain
        self.test_email_domain = os.getenv("TEST_EMAIL_DOMAIN", "")

        # Determine which service to use
        if self.mailosaur_api_key and self.mailosaur_server_id:
            self.service = "mailosaur"
        elif self.mailtrap_api_token and self.mailtrap_inbox_id:
            self.service = "mailtrap"
        elif self.use_mailtm:
            self.service = "mailtm"
            self.mailtm_token = None
            self.mailtm_account_id = None
        else:
            self.service = None

    def is_configured(self) -> bool:
        """Check if email capture service is properly configured"""
        return self.service is not None

    async def get_test_email(self, base_email: str) -> str:
        """
        Generate a test email address for the configured service

        Args:
            base_email: Base email identifier (e.g., 'test_user')

        Returns:
            Full test email address
        """
        if self.service == "mailtm":
            # Create account on mail.tm
            return await self._create_mailtm_account(base_email)

        if not self.test_email_domain:
            raise ValueError("TEST_EMAIL_DOMAIN not configured")

        # Remove @ if present in domain
        domain = self.test_email_domain.lstrip("@")

        # Add unique identifier to avoid conflicts
        timestamp = int(time.time())
        return f"{base_email}_{timestamp}@{domain}"

    async def wait_for_email(
        self, to_email: str, subject_contains: str = "", timeout: int = 30
    ) -> dict | None:
        """
        Wait for an email to arrive in the test inbox

        Args:
            to_email: Email address to check
            subject_contains: Text that should appear in subject (optional)
            timeout: Maximum time to wait in seconds

        Returns:
            Email data dict or None if timeout
        """
        if self.service == "mailosaur":
            return await self._wait_for_email_mailosaur(
                to_email, subject_contains, timeout
            )
        elif self.service == "mailtrap":
            return await self._wait_for_email_mailtrap(
                to_email, subject_contains, timeout
            )
        elif self.service == "mailtm":
            return await self._wait_for_email_mailtm(
                to_email, subject_contains, timeout
            )
        else:
            raise ValueError("No email capture service configured")

    async def _create_mailtm_account(self, base_name: str) -> str:
        """Create a temporary email account on mail.tm (free service)"""
        import random
        import string

        # Retry up to 3 times in case of rate limiting
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    # Get available domains
                    response = await client.get(
                        "https://api.mail.tm/domains", timeout=10.0
                    )
                    if response.status_code != 200:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        raise ValueError("Failed to get mail.tm domains")

                    domains = response.json()
                    if not domains or "hydra:member" not in domains:
                        raise ValueError("No domains available from mail.tm")

                    domain = domains["hydra:member"][0]["domain"]

                    # Create random email with longer suffix to avoid conflicts
                    random_suffix = "".join(
                        random.choices(string.ascii_lowercase + string.digits, k=12)
                    )
                    email_address = f"{base_name}_{random_suffix}@{domain}"
                    password = "".join(
                        random.choices(string.ascii_letters + string.digits, k=16)
                    )

                    # Create account
                    response = await client.post(
                        "https://api.mail.tm/accounts",
                        json={"address": email_address, "password": password},
                        timeout=10.0,
                    )

                    if response.status_code != 201:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        raise ValueError(
                            f"Failed to create mail.tm account after {max_retries} attempts"
                        )

                    # Get auth token
                    response = await client.post(
                        "https://api.mail.tm/token",
                        json={"address": email_address, "password": password},
                        timeout=10.0,
                    )

                    if response.status_code != 200:
                        raise ValueError("Failed to authenticate with mail.tm")

                    token_data = response.json()
                    self.mailtm_token = token_data.get("token")
                    self.mailtm_account_id = token_data.get("id")

                    print(f"📧 Created mail.tm account: {email_address}")
                    return email_address

            except Exception:
                if attempt < max_retries - 1:
                    print(f"⚠ mail.tm attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(2)
                    continue
                raise

        raise ValueError(
            f"Failed to create mail.tm account after {max_retries} attempts"
        )

    async def _wait_for_email_mailtm(
        self, to_email: str, subject_contains: str, timeout: int
    ) -> dict | None:
        """Wait for email using mail.tm API (free service)"""
        if not self.mailtm_token:
            raise ValueError("mail.tm token not available - account not created")

        async with httpx.AsyncClient() as client:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Get messages
                    response = await client.get(
                        "https://api.mail.tm/messages",
                        headers={"Authorization": f"Bearer {self.mailtm_token}"},
                        timeout=10.0,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        messages = data.get("hydra:member", [])

                        # Find matching email
                        for msg in messages:
                            msg_to_list = msg.get("to", [])
                            msg_to = (
                                msg_to_list[0].get("address", "") if msg_to_list else ""
                            )
                            subject = msg.get("subject", "")

                            if to_email.lower() == msg_to.lower() and (
                                not subject_contains
                                or subject_contains.lower() in subject.lower()
                            ):
                                # Get full message
                                msg_id = msg.get("id")
                                msg_response = await client.get(
                                    f"https://api.mail.tm/messages/{msg_id}",
                                    headers={
                                        "Authorization": f"Bearer {self.mailtm_token}"
                                    },
                                    timeout=10.0,
                                )

                                if msg_response.status_code == 200:
                                    return msg_response.json()

                except Exception as e:
                    print(f"Error checking mail.tm: {e}")

                # Wait before next check
                await asyncio.sleep(2)

            return None

    async def _wait_for_email_mailosaur(
        self, to_email: str, subject_contains: str, timeout: int
    ) -> dict | None:
        """Wait for email using Mailosaur API"""
        async with httpx.AsyncClient() as client:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Search for messages
                    response = await client.get(
                        "https://mailosaur.com/api/messages",
                        params={
                            "server": self.mailosaur_server_id,
                            "receivedAfter": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ",
                                time.gmtime(start_time - 10),
                            ),
                        },
                        auth=(self.mailosaur_api_key, ""),
                        timeout=10.0,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        messages = data.get("items", [])

                        # Find matching email
                        for msg in messages:
                            recipients = msg.get("to", [])
                            msg_to_emails = [r.get("email", "") for r in recipients]

                            subject = msg.get("subject", "")

                            if to_email.lower() in [
                                e.lower() for e in msg_to_emails
                            ] and (
                                not subject_contains
                                or subject_contains.lower() in subject.lower()
                            ):
                                # Get full message details
                                msg_id = msg.get("id")
                                msg_response = await client.get(
                                    f"https://mailosaur.com/api/messages/{msg_id}",
                                    auth=(self.mailosaur_api_key, ""),
                                    timeout=10.0,
                                )

                                if msg_response.status_code == 200:
                                    return msg_response.json()

                except Exception as e:
                    print(f"Error checking Mailosaur: {e}")

                # Wait before next check
                await asyncio.sleep(2)

            return None

    async def _wait_for_email_mailtrap(
        self, to_email: str, subject_contains: str, timeout: int
    ) -> dict | None:
        """Wait for email using Mailtrap API"""
        async with httpx.AsyncClient() as client:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Get messages from inbox
                    response = await client.get(
                        f"https://mailtrap.io/api/accounts/{self.mailtrap_inbox_id}/inboxes/{self.mailtrap_inbox_id}/messages",
                        headers={"Api-Token": self.mailtrap_api_token},
                        timeout=10.0,
                    )

                    if response.status_code == 200:
                        messages = response.json()

                        # Find matching email
                        for msg in messages:
                            msg_to_emails = [msg.get("to_email", "")]
                            subject = msg.get("subject", "")

                            if to_email.lower() in [
                                e.lower() for e in msg_to_emails
                            ] and (
                                not subject_contains
                                or subject_contains.lower() in subject.lower()
                            ):
                                # Get full message
                                msg_id = msg.get("id")
                                msg_response = await client.get(
                                    f"https://mailtrap.io/api/accounts/{self.mailtrap_inbox_id}/inboxes/{self.mailtrap_inbox_id}/messages/{msg_id}/body.html",
                                    headers={"Api-Token": self.mailtrap_api_token},
                                    timeout=10.0,
                                )

                                if msg_response.status_code == 200:
                                    msg["html_body"] = msg_response.text
                                    return msg

                except Exception as e:
                    print(f"Error checking Mailtrap: {e}")

                # Wait before next check
                await asyncio.sleep(2)

            return None

    def extract_magic_link(self, email_data: dict) -> str | None:
        """
        Extract magic link URL from email

        Args:
            email_data: Email data from API

        Returns:
            Magic link URL or None if not found
        """
        if self.service == "mailosaur":
            return self._extract_link_mailosaur(email_data, "magic-link-register")
        elif self.service == "mailtrap":
            return self._extract_link_mailtrap(email_data, "magic-link-register")
        elif self.service == "mailtm":
            return self._extract_link_mailtm(email_data, "magic-link-register")
        return None

    def extract_temp_password(self, email_data: dict) -> str | None:
        """
        Extract temporary password from email

        Args:
            email_data: Email data from API

        Returns:
            Temporary password or None if not found
        """
        text_body = self._get_text_body(email_data)
        if not text_body:
            return None

        # Look for temp password pattern
        # Format: "Temporary Password: ABC123xyz"
        match = re.search(r"Temporary Password:\s*([A-Za-z0-9]+)", text_body)
        if match:
            return match.group(1)

        return None

    def _extract_link_mailosaur(
        self, email_data: dict, url_contains: str
    ) -> str | None:
        """Extract URL from Mailosaur email data"""
        html_body = email_data.get("html", {}).get("body", "")
        text_body = email_data.get("text", {}).get("body", "")

        # Try to find link in HTML
        if html_body:
            match = re.search(
                r'href="([^"]*' + re.escape(url_contains) + r'[^"]*)"', html_body
            )
            if match:
                return match.group(1)

        # Try to find link in text
        if text_body:
            match = re.search(
                r"https?://[^\s]*" + re.escape(url_contains) + r"[^\s]*", text_body
            )
            if match:
                return match.group(0)

        return None

    def _extract_link_mailtrap(self, email_data: dict, url_contains: str) -> str | None:
        """Extract URL from Mailtrap email data"""
        html_body = email_data.get("html_body", "")

        if html_body:
            match = re.search(
                r'href="([^"]*' + re.escape(url_contains) + r'[^"]*)"', html_body
            )
            if match:
                return match.group(1)

        return None

    def _extract_link_mailtm(self, email_data: dict, url_contains: str) -> str | None:
        """Extract URL from mail.tm email data"""
        html_body = (
            email_data.get("html", [""])[0]
            if isinstance(email_data.get("html"), list)
            else email_data.get("html", "")
        )
        text_body = email_data.get("text", "")

        # Try HTML first
        if html_body:
            match = re.search(
                r'href="([^"]*' + re.escape(url_contains) + r'[^"]*)"', html_body
            )
            if match:
                return match.group(1)

        # Try text body
        if text_body:
            match = re.search(
                r"https?://[^\s]*" + re.escape(url_contains) + r"[^\s]*", text_body
            )
            if match:
                return match.group(0)

        return None

    def _get_text_body(self, email_data: dict) -> str:
        """Get text body from email data"""
        if self.service == "mailosaur":
            return email_data.get("text", {}).get("body", "")
        elif self.service == "mailtrap":
            return email_data.get("text_body", "")
        elif self.service == "mailtm":
            return email_data.get("text", "")
        return ""
