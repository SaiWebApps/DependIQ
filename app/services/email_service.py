"""
Email service for sending transactional emails
"""

import logging
import os

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service for sending transactional emails

    In development: Logs emails to console
    In production: Can be configured to use SendGrid, AWS SES, etc.
    """

    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "dependiq")
        self.email_service = os.getenv("EMAIL_SERVICE", "gmail")  # gmail or sendgrid
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        # Gmail SMTP settings
        self.gmail_user = os.getenv("GMAIL_USER")
        self.gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
        self.from_email = self.gmail_user or os.getenv(
            "EMAIL_FROM", "noreply@example.com"
        )

    async def send_magic_link(
        self, to_email: str, magic_link_url: str, temp_password: str
    ) -> bool:
        """
        Send registration link email

        Args:
            to_email: Recipient email address
            magic_link_url: Complete URL for registration link
            temp_password: Temporary password for verification

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Complete Your dependiq Registration"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #1976d2;">Welcome to dependiq!</h1>

                <p>Thank you for starting your registration. Click the button below to complete your account setup:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{magic_link_url}"
                       style="background-color: #1976d2; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Complete Registration
                    </a>
                </div>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: #f5f5f5; padding: 10px; border-radius: 5px;">
                    {magic_link_url}
                </p>

                <div style="margin-top: 30px; padding: 15px; background: #e3f2fd; border-radius: 5px;">
                    <p style="margin: 0;"><strong>Temporary Password:</strong></p>
                    <p style="font-family: monospace; font-size: 16px; margin: 10px 0;">
                        {temp_password}
                    </p>
                    <p style="margin: 0; font-size: 14px; color: #666;">
                        You'll need to enter this password when you click the link above.
                    </p>
                </div>

                <p style="margin-top: 30px; font-size: 14px; color: #666;">
                    This link will expire in 24 hours for security reasons.
                </p>

                <p style="margin-top: 30px; font-size: 14px; color: #666;">
                    If you didn't request this registration, you can safely ignore this email.
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; text-align: center;">
                    This is an automated email from dependiq. Please do not reply.
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Welcome to dependiq!

        Thank you for starting your registration. Complete your account setup by visiting:
        {magic_link_url}

        Temporary Password: {temp_password}

        You'll need to enter this password when you click the link above.

        This link will expire in 24 hours for security reasons.

        If you didn't request this registration, you can safely ignore this email.
        """

        return await self._send_email(
            to_email=to_email, subject=subject, html_body=html_body, text_body=text_body
        )

    async def send_verification_email(
        self, to_email: str, verification_url: str
    ) -> bool:
        """
        Send email verification link

        Args:
            to_email: Recipient email address
            verification_url: Complete URL for email verification

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Verify Your Email Address"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #1976d2;">Verify Your Email</h1>

                <p>Please verify your email address to complete your registration:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}"
                       style="background-color: #1976d2; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Verify Email
                    </a>
                </div>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: #f5f5f5; padding: 10px; border-radius: 5px;">
                    {verification_url}
                </p>

                <p style="margin-top: 30px; font-size: 14px; color: #666;">
                    This link will expire in 24 hours for security reasons.
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Verify Your Email

        Please verify your email address by visiting:
        {verification_url}

        This link will expire in 24 hours for security reasons.
        """

        return await self._send_email(
            to_email=to_email, subject=subject, html_body=html_body, text_body=text_body
        )

    async def send_password_reset(self, to_email: str, reset_url: str) -> bool:
        """
        Send password reset link

        Args:
            to_email: Recipient email address
            reset_url: Complete URL for password reset

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Reset Your Password"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #1976d2;">Reset Your Password</h1>

                <p>We received a request to reset your password. Click the button below to create a new password:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}"
                       style="background-color: #1976d2; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </div>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: #f5f5f5; padding: 10px; border-radius: 5px;">
                    {reset_url}
                </p>

                <p style="margin-top: 30px; font-size: 14px; color: #666;">
                    This link will expire in 1 hour for security reasons.
                </p>

                <p style="margin-top: 20px; font-size: 14px; color: #666;">
                    If you didn't request this password reset, you can safely ignore this email.
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Reset Your Password

        We received a request to reset your password. Visit the following link to create a new password:
        {reset_url}

        This link will expire in 1 hour for security reasons.

        If you didn't request this password reset, you can safely ignore this email.
        """

        return await self._send_email(
            to_email=to_email, subject=subject, html_body=html_body, text_body=text_body
        )

    async def _send_email(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> bool:
        """
        Internal method to send email

        Priority: Use configured email service if API key is available
        Fallback: Log to console in development mode
        """
        try:
            # Try to send via configured service if API key is available
            if (
                self.email_service == "gmail"
                and self.gmail_user
                and self.gmail_app_password
            ):
                # Use Gmail SMTP
                return await self._send_with_gmail(
                    to_email, subject, html_body, text_body
                )
            elif self.email_service == "sendgrid" and self.sendgrid_api_key:
                # Use SendGrid
                return await self._send_with_sendgrid(
                    to_email, subject, html_body, text_body
                )
            else:
                # No email service configured - log to console (development mode)
                logger.info(f"\n{'='*80}")
                logger.info("📧 EMAIL (Development Mode - No Email Service Configured)")
                logger.info(f"{'='*80}")
                logger.info(f"To: {to_email}")
                logger.info(f"From: {self.from_name} <{self.from_email}>")
                logger.info(f"Subject: {subject}")
                logger.info(f"{'-'*80}")
                logger.info(f"Text Body:\n{text_body}")
                logger.info(f"{'='*80}\n")

                # Also print to stdout so it's visible in terminal
                print(f"\n{'='*80}")
                print("📧 EMAIL SENT (Development Mode)")
                print(f"{'='*80}")
                print(f"To: {to_email}")
                print(f"Subject: {subject}")
                print(f"{'-'*80}")
                print(text_body)
                print(f"{'='*80}\n")

                logger.warning(
                    "Set GMAIL_USER/GMAIL_APP_PASSWORD or SENDGRID_API_KEY environment variable to enable real email sending."
                )
                return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e!s}")
            return False

    async def _send_with_sendgrid(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> bool:
        """Send email using SendGrid API"""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Content, Email, Mail, To

            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=Content("text/plain", text_body),
                html_content=Content("text/html", html_body),
            )

            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)

            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Email sent successfully to {to_email}")
                return True
            else:
                logger.error(f"SendGrid returned status {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"SendGrid error: {e!s}")
            return False

    async def _send_with_gmail(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> bool:
        """Send email using Gmail SMTP"""
        try:
            import asyncio
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.from_name} <{self.gmail_user}>"
            msg["To"] = to_email
            msg["Subject"] = subject

            # Add text and HTML parts
            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            # Send email using asyncio to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._send_gmail_sync, to_email, msg.as_string()
            )

            logger.info(f"Email sent successfully to {to_email} via Gmail SMTP")
            return True

        except Exception as e:
            logger.error(f"Gmail SMTP error: {e!s}")
            return False

    def _send_gmail_sync(self, to_email: str, msg_string: str):
        """Synchronous Gmail SMTP send (called in executor)"""
        import smtplib

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(self.gmail_user, self.gmail_app_password)
            server.sendmail(self.gmail_user, to_email, msg_string)
