"""
JWT token service for authentication
"""

from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError

from ..config import Config


def create_access_token(user_id: str, email: str) -> str:
    """
    Create a JWT access token

    Args:
        user_id: User ID
        email: User email

    Returns:
        JWT access token string
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }

    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)

    return token


def create_refresh_token(user_id: str) -> str:
    """
    Create a JWT refresh token

    Args:
        user_id: User ID

    Returns:
        JWT refresh token string
    """
    expire = datetime.now(UTC) + timedelta(days=Config.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
    }

    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)

    return token


def verify_token(token: str, token_type: str = "access") -> dict | None:
    """
    Verify and decode a JWT token

    Args:
        token: JWT token string
        token_type: Expected token type ('access' or 'refresh')

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM]
        )

        # Verify token type
        if payload.get("type") != token_type:
            return None

        return payload

    except InvalidTokenError:
        return None


def decode_token(token: str) -> dict | None:
    """
    Decode a JWT token without verification (for inspection)

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=[Config.JWT_ALGORITHM],
            options={"verify_signature": False},
        )
        return payload
    except InvalidTokenError:
        return None


def get_user_id_from_token(token: str) -> str | None:
    """
    Extract user ID from a JWT token

    Args:
        token: JWT token string

    Returns:
        User ID or None if invalid
    """
    payload = verify_token(token)
    if payload:
        return payload.get("sub")
    return None
