"""
Tier 2 tests: Fernet seal/unseal round-trip with REAL cryptography, ZERO mocks.
"""

import json

import pytest
from cryptography.fernet import Fernet, InvalidToken
from workos.session import seal_session_from_auth_response

from app.services.workos_auth import SESSION_COOKIE_NAME


class TestSealUnseal:

    def test_seal_produces_encrypted_output(self, fernet_key, make_access_token):
        token = make_access_token()
        sealed = seal_session_from_auth_response(
            access_token=token,
            refresh_token="rt_test_abc123",
            user={"id": "user_01", "email": "a@b.com"},
            cookie_password=fernet_key,
        )

        assert sealed != token
        assert "user_01" not in sealed
        assert "a@b.com" not in sealed
        assert len(sealed) > 100

    def test_seal_unseal_round_trip(self, fernet_key, make_access_token):
        token = make_access_token(user_id="user_42")
        sealed = seal_session_from_auth_response(
            access_token=token,
            refresh_token="rt_xyz",
            user={"id": "user_42", "email": "test@x.com"},
            cookie_password=fernet_key,
        )

        f = Fernet(fernet_key)
        decrypted = json.loads(f.decrypt(sealed.encode()))
        assert decrypted["access_token"] == token
        assert decrypted["refresh_token"] == "rt_xyz"
        assert decrypted["user"]["id"] == "user_42"
        assert decrypted["user"]["email"] == "test@x.com"

    def test_wrong_key_cannot_unseal(self, fernet_key, make_access_token):
        token = make_access_token()
        sealed = seal_session_from_auth_response(
            access_token=token,
            refresh_token="rt_test_abc",
            user={"id": "u1", "email": "x@y.com"},
            cookie_password=fernet_key,
        )

        wrong_key = Fernet.generate_key().decode()
        f = Fernet(wrong_key)
        with pytest.raises(InvalidToken):
            f.decrypt(sealed.encode())

    def test_tampered_cookie_fails(self, fernet_key, make_access_token):
        token = make_access_token()
        sealed = seal_session_from_auth_response(
            access_token=token,
            refresh_token="rt_test_abc",
            user={"id": "u1", "email": "x@y.com"},
            cookie_password=fernet_key,
        )

        tampered = sealed[:-5] + "ZZZZZ"
        f = Fernet(fernet_key)
        with pytest.raises(InvalidToken):
            f.decrypt(tampered.encode())

    def test_empty_cookie_password_raises(self, make_access_token):
        with pytest.raises(ValueError):
            seal_session_from_auth_response(
                access_token=make_access_token(),
                refresh_token="rt",
                user={"id": "u", "email": "e@e.com"},
                cookie_password="",
            )

    def test_session_cookie_name_is_constant(self):
        assert SESSION_COOKIE_NAME == "diq_session"
