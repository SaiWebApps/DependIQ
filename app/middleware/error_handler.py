"""
Enhanced error handling middleware for better user feedback
"""

import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Custom authentication error"""

    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthorizationError(Exception):
    """Custom authorization error"""

    def __init__(self, message: str = "Insufficient permissions"):
        self.message = message
        super().__init__(self.message)


class ResourceNotFoundError(Exception):
    """Custom resource not found error"""

    def __init__(self, resource: str, identifier: str | None = None):
        self.resource = resource
        self.identifier = identifier
        if identifier:
            self.message = f"{resource} with ID '{identifier}' not found"
        else:
            self.message = f"{resource} not found"
        super().__init__(self.message)


class ValidationError(Exception):
    """Custom validation error"""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors with user-friendly messages"""
    logger.warning(f"Authentication error: {exc.message} - Path: {request.url.path}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "Authentication Failed",
            "message": exc.message,
            "type": "authentication_error",
            "details": {"path": str(request.url.path), "method": request.method},
        },
    )


async def authorization_error_handler(request: Request, exc: AuthorizationError):
    """Handle authorization errors"""
    logger.warning(
        f"Authorization error: {exc.message} - User: {request.state.user if hasattr(request.state, 'user') else 'Unknown'}"
    )

    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "Access Denied",
            "message": exc.message,
            "type": "authorization_error",
            "help": "You don't have permission to access this resource.",
        },
    )


async def resource_not_found_handler(request: Request, exc: ResourceNotFoundError):
    """Handle resource not found errors"""
    logger.info(f"Resource not found: {exc.message}")

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Resource Not Found",
            "message": exc.message,
            "type": "not_found_error",
            "resource": exc.resource,
            "identifier": exc.identifier,
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed feedback"""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({"field": field, "message": error["msg"], "type": error["type"]})

    logger.info(f"Validation error: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "The request contains invalid data",
            "type": "validation_error",
            "errors": errors,
            "help": "Please check the highlighted fields and try again.",
        },
    )


async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Handle database errors"""
    logger.error(f"Database error: {exc!s}", exc_info=True)

    # Handle specific database errors
    if isinstance(exc, IntegrityError):
        # Extract constraint name if available
        error_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)

        if (
            "unique constraint" in error_msg.lower()
            or "duplicate key" in error_msg.lower()
        ):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "Duplicate Entry",
                    "message": "This record already exists in the database",
                    "type": "integrity_error",
                    "help": "Please use a different value for unique fields.",
                },
            )

    # Generic database error
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database Error",
            "message": "An error occurred while processing your request",
            "type": "database_error",
            "help": "Please try again. If the problem persists, contact support.",
        },
    )


async def jwt_error_handler(request: Request, exc: InvalidTokenError):
    """Handle JWT token errors"""
    logger.warning(f"JWT error: {exc!s}")

    if isinstance(exc, ExpiredSignatureError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "Token Expired",
                "message": "Your session has expired. Please log in again.",
                "type": "token_expired",
                "action": "refresh_required",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": "Invalid Token",
            "message": "Authentication token is invalid or malformed",
            "type": "invalid_token",
            "action": "login_required",
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPExceptions — preserve FastAPI's standard response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def generic_error_handler(request: Request, exc: Exception):
    """Handle all other unhandled exceptions"""
    logger.error(f"Unhandled exception: {exc!s}", exc_info=True)

    # Don't expose internal error details in production
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred while processing your request",
            "type": "internal_error",
            "help": "Please try again. If the problem persists, contact support.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def register_error_handlers(app):
    """
    Register all error handlers with the FastAPI application

    Usage:
        from app.middleware.error_handler import register_error_handlers
        register_error_handlers(app)
    """
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(AuthenticationError, authentication_error_handler)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(ResourceNotFoundError, resource_not_found_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(InvalidTokenError, jwt_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    logger.info("Error handlers registered successfully")


# User-friendly error messages mapping
ERROR_MESSAGES = {
    # Authentication
    "invalid_credentials": "The email or password you entered is incorrect",
    "account_disabled": "Your account has been disabled. Please contact support",
    "email_not_verified": "Please verify your email address before logging in",
    "token_expired": "Your session has expired. Please log in again",
    "invalid_token": "Invalid authentication token. Please log in again",
    # Authorization
    "insufficient_permissions": "You don't have permission to perform this action",
    "account_locked": "Your account has been locked. Please contact support",
    # Validation
    "email_invalid": "Please enter a valid email address",
    "password_weak": "Password must be at least 8 characters with uppercase, lowercase, number, and special character",
    "email_taken": "This email address is already registered",
    "required_field": "This field is required",
    # Resources
    "user_not_found": "User account not found",
    "project_not_found": "Project not found or you don't have access to it",
    "session_expired": "Your session has expired. Please start over",
    # Operations
    "upload_failed": "Failed to upload file. Please try again",
    "analysis_failed": "Project analysis failed. Please check your file and try again",
    "update_failed": "Failed to update dependencies. Please try again",
    "email_send_failed": "Failed to send email. Please try again later",
    # Database
    "database_error": "A database error occurred. Please try again",
    "duplicate_entry": "This record already exists",
    "foreign_key_violation": "Cannot delete this record because it is referenced by other records",
    # Rate limiting
    "rate_limit_exceeded": "Too many requests. Please wait a moment and try again",
    # General
    "internal_error": "An unexpected error occurred. Please try again",
    "maintenance_mode": "The system is currently undergoing maintenance. Please try again later",
    "service_unavailable": "Service temporarily unavailable. Please try again later",
}


def get_user_friendly_message(error_code: str) -> str:
    """
    Get a user-friendly error message for a given error code

    Args:
        error_code: Error code to look up

    Returns:
        User-friendly error message
    """
    return ERROR_MESSAGES.get(error_code, "An error occurred. Please try again.")
