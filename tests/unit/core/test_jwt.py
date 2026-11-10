import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security.jwt import create_access_token, create_refresh_token, decode_token


def _claims(**overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": "1",
        "sv": 0,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _signed(claims: dict, key: str = settings.SECRET_KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class TestJWT:
    def test_create_and_decode_access_token(self):
        payload = decode_token(create_access_token(subject="42", session_version=3))

        assert payload["sub"] == "42"
        assert payload["sv"] == 3
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_and_decode_refresh_token(self):
        payload = decode_token(create_refresh_token(subject="42", session_version=3))

        assert payload["sub"] == "42"
        assert payload["sv"] == 3
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_every_token_has_its_own_id(self):
        first = decode_token(create_access_token(subject="1"))
        second = decode_token(create_access_token(subject="1"))
        assert first["jti"] != second["jti"]

    def test_lifetimes_come_from_the_settings(self):
        access = decode_token(create_access_token(subject="1"))
        refresh = decode_token(create_refresh_token(subject="1"))

        assert access["exp"] - access["iat"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert refresh["exp"] - refresh["iat"] == settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    @pytest.mark.parametrize(("expired_seconds_ago", "accepted"), [(10, True), (60, False)])
    def test_expiry_has_30_seconds_of_leeway(self, expired_seconds_ago, accepted):
        # Clock skew between servers: a token that expired a few seconds ago still passes.
        now = datetime.now(UTC)
        token = _signed(
            _claims(
                iat=now - timedelta(minutes=5), exp=now - timedelta(seconds=expired_seconds_ago)
            )
        )
        if accepted:
            assert decode_token(token)["sub"] == "1"
        else:
            with pytest.raises(jwt.ExpiredSignatureError):
                decode_token(token)


class TestForgedTokensAreRejected:
    """Each case is a token an attacker can build without the key, or a claim left out."""

    def test_garbage(self):
        with pytest.raises(jwt.PyJWTError):
            decode_token("invalid.token.here")

    def test_signed_with_another_key(self):
        token = _signed(_claims(), key="another-key-of-at-least-32-bytes-0123456789")
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(token)

    def test_signature_stripped(self):
        header, payload, _ = _signed(_claims()).split(".")
        with pytest.raises(jwt.PyJWTError):
            decode_token(f"{header}.{payload}.")

    def test_payload_changed_after_signing(self):
        header, _, signature = _signed(_claims(sub="1")).split(".")
        tampered = _b64(json.loads(json.dumps(_claims(sub="2"), default=lambda d: d.timestamp())))
        with pytest.raises(jwt.PyJWTError):
            decode_token(f"{header}.{tampered}.{signature}")

    def test_algorithm_none(self):
        claims = _claims()
        claims["iat"], claims["exp"] = claims["iat"].timestamp(), claims["exp"].timestamp()
        token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
        with pytest.raises(jwt.PyJWTError):
            decode_token(token)

    @pytest.mark.filterwarnings("ignore:The HMAC key")  # the test key is short for SHA-512
    def test_another_algorithm_with_the_same_key(self):
        with pytest.raises(jwt.InvalidAlgorithmError):
            decode_token(_signed(_claims(), algorithm="HS512"))

    @pytest.mark.parametrize("claim", ["exp", "iat", "sub", "jti", "sv"])
    def test_a_required_claim_is_missing(self, claim: str):
        with pytest.raises(jwt.MissingRequiredClaimError):
            decode_token(_signed(_claims(**{claim: None})))

    def test_expired(self):
        now = datetime.now(UTC)
        token = _signed(_claims(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1)))
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    def test_issued_in_the_future(self):
        token = _signed(_claims(iat=datetime.now(UTC) + timedelta(hours=1)))
        with pytest.raises(jwt.ImmatureSignatureError):
            decode_token(token)
