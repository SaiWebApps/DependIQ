"""
Authentication service for user registration, login, and token management
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    EmailVerificationToken,
    MagicLinkToken,
    PasswordResetToken,
    User,
    UserPreference,
)
from ..utils.password_utils import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from .email_service import EmailService
from .token_service import create_access_token, create_refresh_token, verify_token


class AuthService:
    """Service for handling authentication operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_user(
        self, email: str, password: str, confirm_password: str
    ) -> tuple[User | None, str | None]:
        """
        Register a new user with email and password

        Args:
            email: User email address
            password: User password
            confirm_password: Password confirmation

        Returns:
            Tuple of (User object, error message)
        """
        # Validate email format
        email = email.lower().strip()
        if not email or "@" not in email:
            return None, "Invalid email address"

        # Validate passwords match
        if password != confirm_password:
            return None, "Passwords do not match"

        # Validate password strength
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            return None, error_msg

        # Check if user already exists
        result = await self.db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            return None, "An account with this email already exists"

        try:
            # Create user
            user = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=False,
                is_active=True,
            )
            self.db.add(user)
            await self.db.flush()  # Flush to get user.id

            # Create default preferences
            preferences = UserPreference(
                user_id=user.id,
                theme="light",
                language="en",
                timezone="UTC",
                notifications_enabled=True,
            )
            self.db.add(preferences)

            # Create email verification token
            verification_token = self._create_verification_token(user.id)
            self.db.add(verification_token)

            await self.db.commit()
            await self.db.refresh(user)

            # Send verification email
            email_service = EmailService()
            base_url = os.getenv("BASE_URL", "http://localhost:8000")
            verification_url = (
                f"{base_url}/api/auth/verify-email?token={verification_token.token}"
            )

            await email_service.send_verification_email(
                to_email=email, verification_url=verification_url
            )

            return user, None

        except IntegrityError:
            await self.db.rollback()
            return None, "An account with this email already exists"
        except Exception as e:
            await self.db.rollback()
            return None, f"Registration failed: {e!s}"

    async def login_user(
        self, email: str, password: str
    ) -> tuple[dict | None, str | None]:
        """
        Authenticate user with email and password

        Args:
            email: User email address
            password: User password

        Returns:
            Tuple of (auth tokens dict, error message)
        """
        email = email.lower().strip()

        # Find user
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return None, "Invalid email or password"

        # Check if user has a password (might be OAuth-only)
        if not user.password_hash:
            return (
                None,
                "This account uses OAuth login. Please sign in with your linked provider.",
            )

        # Verify password
        if not verify_password(password, user.password_hash):
            return None, "Invalid email or password"

        # Check if account is active
        if not user.is_active:
            return None, "Account is disabled. Please contact support."

        # Update last login time
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        # Generate tokens
        access_token = create_access_token(str(user.id), user.email)
        refresh_token = create_refresh_token(str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 900,  # 15 minutes
            "user": user.to_dict(),
        }, None

    async def refresh_access_token(
        self, refresh_token: str
    ) -> tuple[str | None, str | None]:
        """
        Generate new access token from refresh token

        Args:
            refresh_token: JWT refresh token

        Returns:
            Tuple of (new access token, error message)
        """
        # Verify refresh token
        payload = verify_token(refresh_token, token_type="refresh")
        if not payload:
            return None, "Invalid or expired refresh token"

        user_id = payload.get("sub")

        # Convert string UUID to UUID object
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, AttributeError, TypeError):
            return None, "Invalid user ID in token"

        # Get user
        result = await self.db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return None, "User not found or inactive"

        # Generate new access token
        access_token = create_access_token(str(user.id), user.email)

        return access_token, None

    async def verify_email(self, token: str) -> tuple[bool, str | None]:
        """
        Verify user email with token

        Args:
            token: Email verification token

        Returns:
            Tuple of (success boolean, error message)
        """
        result = await self.db.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
        verification = result.scalar_one_or_none()

        if not verification:
            return False, "Invalid verification token"

        if verification.is_used():
            return False, "Verification token has already been used"

        if verification.is_expired():
            return False, "Verification token has expired"

        # Get user
        result = await self.db.execute(
            select(User).where(User.id == verification.user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False, "User not found"

        # Mark email as verified
        user.email_verified = True
        verification.used_at = datetime.utcnow()

        await self.db.commit()

        return True, None

    async def request_password_reset(self, email: str) -> tuple[str | None, str | None]:
        """
        Request password reset for user

        Args:
            email: User email address

        Returns:
            Tuple of (reset token, error message)
        """
        email = email.lower().strip()

        # Find user
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        # Always return success to prevent email enumeration
        if not user:
            return None, None

        # Check if user has a password (OAuth-only users can't reset)
        if not user.password_hash:
            return None, None

        # Create reset token
        reset_token = self._create_reset_token(user.id)
        self.db.add(reset_token)
        await self.db.commit()

        # Send password reset email
        email_service = EmailService()
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        reset_url = f"{base_url}/login?reset_token={reset_token.token}"
        # Note: In production, create a proper password reset page
        # For now, direct to login with token parameter

        await email_service.send_password_reset(to_email=email, reset_url=reset_url)

        return reset_token.token, None

    async def reset_password(
        self, token: str, new_password: str, confirm_password: str
    ) -> tuple[bool, str | None]:
        """
        Reset user password with token

        Args:
            token: Password reset token
            new_password: New password
            confirm_password: Password confirmation

        Returns:
            Tuple of (success boolean, error message)
        """
        # Validate passwords match
        if new_password != confirm_password:
            return False, "Passwords do not match"

        # Validate password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg

        # Find reset token
        result = await self.db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == token)
        )
        reset = result.scalar_one_or_none()

        if not reset:
            return False, "Invalid reset token"

        if reset.is_used():
            return False, "Reset token has already been used"

        if reset.is_expired():
            return False, "Reset token has expired"

        # Get user
        result = await self.db.execute(select(User).where(User.id == reset.user_id))
        user = result.scalar_one_or_none()

        if not user:
            return False, "User not found"

        # Update password
        user.password_hash = hash_password(new_password)
        reset.used_at = datetime.utcnow()

        await self.db.commit()

        return True, None

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        confirm_password: str,
    ) -> tuple[bool, str | None]:
        """
        Change user password (requires current password)

        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password
            confirm_password: Password confirmation

        Returns:
            Tuple of (success boolean, error message)
        """
        # Validate passwords match
        if new_password != confirm_password:
            return False, "Passwords do not match"

        # Validate password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg

        # Convert string UUID to UUID object if needed
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, AttributeError, TypeError):
            return False, "Invalid user ID"

        # Get user
        result = await self.db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()

        if not user:
            return False, "User not found"

        # Verify current password
        if not user.password_hash:
            return False, "Cannot change password for OAuth-only accounts"

        if not verify_password(current_password, user.password_hash):
            return False, "Current password is incorrect"

        # Update password
        user.password_hash = hash_password(new_password)
        await self.db.commit()

        return True, None

    def _create_verification_token(self, user_id: uuid.UUID) -> EmailVerificationToken:
        """Create email verification token"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        return EmailVerificationToken(
            user_id=user_id, token=token, expires_at=expires_at
        )

    def _create_reset_token(self, user_id: uuid.UUID) -> PasswordResetToken:
        """Create password reset token"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)

        return PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)

    async def check_email_exists(self, email: str) -> tuple[bool, str | None]:
        """
        Check if an email already exists in the system

        Args:
            email: Email address to check

        Returns:
            Tuple of (exists boolean, error message)
        """
        email = email.lower().strip()

        if not email or "@" not in email:
            return False, "Invalid email address"

        # Find user
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        return user is not None, None

    async def send_magic_link(self, email: str) -> tuple[str | None, str | None]:
        """
        Send registration link to new user

        Args:
            email: User email address

        Returns:
            Tuple of (registration link token, error message)
        """
        email = email.lower().strip()

        if not email or "@" not in email:
            return None, "Invalid email address"

        # Check if user already exists
        result = await self.db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            return None, "An account with this email already exists"

        # Generate temp password (simple for now, can be more complex)
        import random
        import string

        temp_password = "".join(
            random.choices(string.ascii_letters + string.digits, k=12)
        )

        # Create registration link token
        magic_token = self._create_magic_link_token(email, temp_password)
        self.db.add(magic_token)
        await self.db.commit()

        # Send email with registration link
        email_service = EmailService()
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        magic_link_url = f"{base_url}/magic-link-register?token={magic_token.token}"

        await email_service.send_magic_link(
            to_email=email, magic_link_url=magic_link_url, temp_password=temp_password
        )

        return magic_token.token, None

    async def complete_magic_link_registration(
        self,
        token: str,
        temp_password: str,
        new_password: str,
        confirm_password: str,
        use_passkey: bool = False,
    ) -> tuple[User | None, str | None]:
        """
        Complete registration via registration link

        Args:
            token: Registration link token from URL
            temp_password: Temporary password from email
            new_password: User's desired new password
            confirm_password: Password confirmation
            use_passkey: Whether to setup passkey instead of password

        Returns:
            Tuple of (User object, error message)
        """
        # Validate passwords match
        if new_password != confirm_password:
            return None, "Passwords do not match"

        # Validate password strength
        if not use_passkey:
            is_valid, error_msg = validate_password_strength(new_password)
            if not is_valid:
                return None, error_msg

        # Find registration link token
        result = await self.db.execute(
            select(MagicLinkToken).where(MagicLinkToken.token == token)
        )
        magic_link = result.scalar_one_or_none()

        if not magic_link:
            return None, "Invalid registration link"

        if magic_link.is_used():
            return None, "This registration link has already been used"

        if magic_link.is_expired():
            return None, "This registration link has expired"

        # Verify temp password
        if magic_link.temp_password != temp_password:
            return None, "Invalid temporary password"

        # Check if user was created in the meantime
        result = await self.db.execute(
            select(User).where(User.email == magic_link.email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            return None, "An account with this email already exists"

        try:
            # Create user
            user = User(
                email=magic_link.email,
                password_hash=hash_password(new_password) if not use_passkey else None,
                email_verified=True,  # Email is verified via registration link
                is_active=True,
            )
            self.db.add(user)
            await self.db.flush()  # Flush to get user.id

            # Create default preferences
            preferences = UserPreference(
                user_id=user.id,
                theme="light",
                language="en",
                timezone="UTC",
                notifications_enabled=True,
            )
            self.db.add(preferences)

            # Mark registration link as used
            magic_link.used_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(user)

            return user, None

        except IntegrityError:
            await self.db.rollback()
            return None, "An account with this email already exists"
        except Exception as e:
            await self.db.rollback()
            return None, f"Registration failed: {e!s}"

    def _create_magic_link_token(
        self, email: str, temp_password: str
    ) -> MagicLinkToken:
        """Create registration link token for new user registration"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        return MagicLinkToken(
            email=email, token=token, temp_password=temp_password, expires_at=expires_at
        )
