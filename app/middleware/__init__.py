"""
Middleware modules for the dependiq application
"""

from .auth_middleware import (
    get_current_active_user,
    get_current_user,
    get_current_user_optional,
    get_current_verified_user,
)
from .error_handler import (
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    get_user_friendly_message,
    register_error_handlers,
)

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "ValidationError",
    "get_current_active_user",
    "get_current_user",
    "get_current_user_optional",
    "get_current_verified_user",
    "get_user_friendly_message",
    "register_error_handlers",
]
