import jwt
import pytest

from app.core.security.jwt import create_access_token, create_refresh_token, decode_token


class TestJWT:
    def test_create_and_decode_access_token(self):
        token = create_access_token(subject="42", scopes=["admin"])
        payload = decode_token(token)

        assert payload["sub"] == "42"
        assert payload["scopes"] == ["admin"]
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token(subject="42")
        payload = decode_token(token)

        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"
        assert "scopes" not in payload

    def test_decode_invalid_token_raises(self):
        with pytest.raises(jwt.PyJWTError):
            decode_token("invalid.token.here")

    def test_access_token_default_scopes_empty(self):
        token = create_access_token(subject="1")
        payload = decode_token(token)
        assert payload["scopes"] == []
