"""The session model end to end: tokens, rotation, reuse, logout, forged tokens."""

import time
import uuid

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.integration.api.helpers import PASSWORD, bearer, login, register

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _me(client: AsyncClient, access_token: str) -> int:
    return (await client.get("/v1/auth/me", headers=bearer(access_token))).status_code


async def _refresh(client: AsyncClient, refresh_token: str):
    return await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})


async def test_register_login_and_me(api_client: AsyncClient):
    created = await register(api_client, "alice")
    tokens = await login(api_client, "alice")

    me = await api_client.get("/v1/auth/me", headers=bearer(tokens["access_token"]))

    assert me.status_code == 200
    assert me.json()["id"] == created["id"]
    assert me.json()["email"] == "alice@example.com"
    assert "password" not in me.text


async def test_login_by_email_and_with_another_case(api_client: AsyncClient):
    await register(api_client, "alice")

    response = await api_client.post(
        "/v1/auth/login", data={"username": "ALICE@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200


async def test_register_twice_is_a_conflict(api_client: AsyncClient):
    await register(api_client, "alice")

    response = await api_client.post(
        "/v1/auth/register",
        json={"email": "alice@example.com", "username": "alice2", "password": PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_wrong_password_and_unknown_account_look_the_same(api_client: AsyncClient):
    await register(api_client, "alice")

    wrong = await api_client.post("/v1/auth/login", data={"username": "alice", "password": "nope"})
    unknown = await api_client.post("/v1/auth/login", data={"username": "nobody", "password": "x"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_refresh_rotates_the_token(api_client: AsyncClient):
    await register(api_client, "alice")
    first = await login(api_client, "alice")

    second = await _refresh(api_client, first["refresh_token"])

    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    assert await _me(api_client, second.json()["access_token"]) == 200


async def test_replaying_a_refresh_token_ends_every_session_of_the_account(
    api_client: AsyncClient,
):
    # A refresh token used twice was stolen. Whoever used it first holds a fresh pair,
    # issued in the same second as the replay: that pair must die too, or the thief
    # keeps the session while the owner is logged out.
    await register(api_client, "alice")
    other_device = await login(api_client, "alice")
    stolen = (await login(api_client, "alice"))["refresh_token"]

    first_use = await _refresh(api_client, stolen)
    replay = await _refresh(api_client, stolen)

    assert first_use.status_code == 200
    assert replay.status_code == 401
    assert replay.json()["code"] == "refresh_token_reused"
    assert await _me(api_client, first_use.json()["access_token"]) == 401
    assert (await _refresh(api_client, first_use.json()["refresh_token"])).status_code == 401
    assert await _me(api_client, other_device["access_token"]) == 401
    # The account itself is fine: logging in starts a new session.
    assert await _me(api_client, (await login(api_client, "alice"))["access_token"]) == 200


async def test_reuse_only_ends_the_sessions_of_that_account(api_client: AsyncClient):
    await register(api_client, "alice")
    await register(api_client, "bob")
    bob = await login(api_client, "bob")
    stolen = (await login(api_client, "alice"))["refresh_token"]

    await _refresh(api_client, stolen)
    await _refresh(api_client, stolen)

    assert await _me(api_client, bob["access_token"]) == 200


async def test_logout_revokes_both_tokens(api_client: AsyncClient):
    await register(api_client, "alice")
    tokens = await login(api_client, "alice")

    response = await api_client.post(
        "/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=bearer(tokens["access_token"]),
    )

    assert response.status_code == 204
    assert await _me(api_client, tokens["access_token"]) == 401
    assert (await _refresh(api_client, tokens["refresh_token"])).status_code == 401


def _forged(user_id: int, key: str, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "type": "access",
        "sv": 0,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 600,
    } | overrides
    return jwt.encode(claims, key, algorithm="HS256")


async def test_a_token_signed_with_another_key_is_rejected(api_client: AsyncClient):
    user = await register(api_client, "alice")

    token = _forged(user["id"], "not-the-key-of-this-deployment-0123456789")

    assert await _me(api_client, token) == 401


async def test_a_token_of_a_past_session_version_is_rejected(api_client: AsyncClient):
    user = await register(api_client, "alice")

    token = _forged(user["id"], settings.SECRET_KEY, sv=7)

    assert await _me(api_client, token) == 401


async def test_a_refresh_token_is_not_an_access_token(api_client: AsyncClient):
    await register(api_client, "alice")
    tokens = await login(api_client, "alice")

    assert await _me(api_client, tokens["refresh_token"]) == 401
