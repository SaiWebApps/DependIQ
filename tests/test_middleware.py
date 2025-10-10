"""
Unit tests for middleware components
"""

import pytest
from fastapi import Request, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.middleware.error_handler import (
    ERROR_MESSAGES,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    authentication_error_handler,
    authorization_error_handler,
    generic_error_handler,
    get_user_friendly_message,
    jwt_error_handler,
    resource_not_found_handler,
)


class TestCustomExceptions:
    """Test custom exception classes"""

    def test_authentication_error(self):
        """Test AuthenticationError exception"""
        error = AuthenticationError("Invalid credentials")
        assert error.message == "Invalid credentials"
        assert error.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authentication_error_custom_status(self):
        """Test AuthenticationError with custom status code"""
        error = AuthenticationError("Token expired", status_code=403)
        assert error.status_code == 403

    def test_authorization_error(self):
        """Test AuthorizationError exception"""
        error = AuthorizationError("Access denied")
        assert error.message == "Access denied"

    def test_resource_not_found_error(self):
        """Test ResourceNotFoundError exception"""
        error = ResourceNotFoundError("User", "123")
        assert error.resource == "User"
        assert error.identifier == "123"
        assert "User with ID '123' not found" in error.message

    def test_resource_not_found_error_no_id(self):
        """Test ResourceNotFoundError without identifier"""
        error = ResourceNotFoundError("Project")
        assert error.resource == "Project"
        assert error.identifier is None
        assert error.message == "Project not found"

    def test_validation_error(self):
        """Test ValidationError exception"""
        error = ValidationError("email", "Invalid format")
        assert error.field == "email"
        assert error.message == "Invalid format"


class TestErrorHandlers:
    """Test error handler functions"""

    @pytest.mark.asyncio
    async def test_authentication_error_handler(self):
        """Test authentication error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "url": "http://test/api/login",
                "headers": [],
                "query_string": b"",
                "path": "/api/login",
            }
        )

        error = AuthenticationError("Invalid credentials")
        response = await authentication_error_handler(request, error)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        body = response.body.decode()
        assert "Invalid credentials" in body
        assert "authentication_error" in body

    @pytest.mark.asyncio
    async def test_authorization_error_handler(self):
        """Test authorization error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "url": "http://test/api/admin",
                "headers": [],
                "query_string": b"",
                "path": "/api/admin",
            }
        )

        error = AuthorizationError("Insufficient permissions")
        response = await authorization_error_handler(request, error)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        body = response.body.decode()
        assert "Insufficient permissions" in body

    @pytest.mark.asyncio
    async def test_resource_not_found_handler(self):
        """Test resource not found error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "url": "http://test/api/user/123",
                "headers": [],
                "query_string": b"",
                "path": "/api/user/123",
            }
        )

        error = ResourceNotFoundError("User", "123")
        response = await resource_not_found_handler(request, error)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.body.decode()
        assert "User" in body
        assert "123" in body

    @pytest.mark.asyncio
    async def test_jwt_error_handler_expired(self):
        """Test JWT expired error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "url": "http://test/api/profile",
                "headers": [],
                "query_string": b"",
                "path": "/api/profile",
            }
        )

        error = ExpiredSignatureError("Signature has expired")
        response = await jwt_error_handler(request, error)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        body = response.body.decode()
        assert "Token Expired" in body or "expired" in body.lower()

    @pytest.mark.asyncio
    async def test_jwt_error_handler_invalid(self):
        """Test JWT invalid error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "url": "http://test/api/profile",
                "headers": [],
                "query_string": b"",
                "path": "/api/profile",
            }
        )

        error = InvalidTokenError("Invalid token")
        response = await jwt_error_handler(request, error)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        body = response.body.decode()
        assert "Invalid Token" in body or "invalid" in body.lower()

    @pytest.mark.asyncio
    async def test_generic_error_handler(self):
        """Test generic error handling"""
        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "url": "http://test/api/endpoint",
                "headers": [],
                "query_string": b"",
                "path": "/api/endpoint",
            }
        )

        error = Exception("Something went wrong")
        response = await generic_error_handler(request, error)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        body = response.body.decode()
        assert "Internal Server Error" in body or "error" in body.lower()


class TestUserFriendlyMessages:
    """Test user-friendly error messages"""

    def test_get_user_friendly_message_known(self):
        """Test getting message for known error code"""
        message = get_user_friendly_message("invalid_credentials")
        assert message == ERROR_MESSAGES["invalid_credentials"]
        assert "email or password" in message.lower()

    def test_get_user_friendly_message_unknown(self):
        """Test getting message for unknown error code"""
        message = get_user_friendly_message("unknown_error_code")
        assert "error occurred" in message.lower()

    def test_all_error_messages_defined(self):
        """Test that all expected error messages are defined"""
        expected_categories = [
            "invalid_credentials",
            "email_invalid",
            "password_weak",
            "user_not_found",
            "database_error",
            "rate_limit_exceeded",
        ]

        for error_code in expected_categories:
            assert error_code in ERROR_MESSAGES
            assert len(ERROR_MESSAGES[error_code]) > 0

    def test_error_messages_are_user_friendly(self):
        """Test that error messages are user-friendly"""
        for code, message in ERROR_MESSAGES.items():
            # Messages should not contain technical jargon
            assert "exception" not in message.lower()
            assert "traceback" not in message.lower()
            assert "stack" not in message.lower()

            # Messages should be helpful
            assert len(message) > 10
            assert message[0].isupper() or message.startswith("(")
