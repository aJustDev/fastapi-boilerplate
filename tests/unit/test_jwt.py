from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
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
        assert payload["scopes"] == []
        assert "jti" in payload

    def test_decode_invalid_token_raises(self):
        with pytest.raises(jwt.PyJWTError):
            decode_token("invalid.token.here")

    def test_access_token_default_scopes_empty(self):
        token = create_access_token(subject="1")
        payload = decode_token(token)
        assert payload["scopes"] == []

    @pytest.mark.parametrize(("expired_seconds_ago", "accepted"), [(10, True), (60, False)])
    def test_expiry_has_30_seconds_of_leeway(self, expired_seconds_ago, accepted):
        # Clock skew between servers: a token that expired a few seconds ago still passes.
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "1",
                "jti": "j",
                "iat": now - timedelta(minutes=5),
                "exp": now - timedelta(seconds=expired_seconds_ago),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        if accepted:
            assert decode_token(token)["sub"] == "1"
        else:
            with pytest.raises(jwt.ExpiredSignatureError):
                decode_token(token)
