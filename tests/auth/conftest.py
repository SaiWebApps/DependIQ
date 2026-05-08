"""
Auth test fixtures — crypto primitives for testing sealed sessions.

Uses the same pattern as WorkOS's own test suite:
generate RSA keypair, sign JWTs, mock JWKS, verify round-trip.
"""

import time
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session")
def fernet_key() -> str:
    """A stable Fernet key for sealing/unsealing test sessions."""
    return Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def rsa_keypair():
    """RSA-2048 keypair for signing/verifying test JWTs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def make_access_token(rsa_keypair):
    """Factory: create a signed JWT with configurable claims and expiry."""

    def _make(
        user_id: str = "user_test_01",
        session_id: str = "sess_test_01",
        org_id: str | None = None,
        expired: bool = False,
        extra_claims: dict | None = None,
    ) -> str:
        private_key, _ = rsa_keypair
        now = int(time.time())
        claims = {
            "sub": user_id,
            "sid": session_id,
            "iat": now,
            "exp": now - 3600 if expired else now + 3600,
        }
        if org_id:
            claims["org_id"] = org_id
        if extra_claims:
            claims.update(extra_claims)
        return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key-1"})

    return _make


@pytest.fixture
def make_sealed_session(fernet_key, make_access_token):
    """Factory: create a complete sealed session cookie value."""
    from workos.session import seal_session_from_auth_response

    def _make(
        user_id: str = "user_test_01",
        email: str = "test@example.com",
        expired: bool = False,
    ) -> str:
        access_token = make_access_token(user_id=user_id, expired=expired)
        return seal_session_from_auth_response(
            access_token=access_token,
            refresh_token="rt_test_abcdef123456",
            user={"id": user_id, "email": email},
            cookie_password=fernet_key,
        )

    return _make


@pytest.fixture
def mock_jwks(rsa_keypair):
    """A mock PyJWKClient that returns our test public key for signature validation."""
    _, public_key = rsa_keypair
    mock_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
    return mock_client
