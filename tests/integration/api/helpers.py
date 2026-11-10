"""Steps shared by the API tests: they go through HTTP like any client."""

from httpx import AsyncClient

PASSWORD = "correct-horse-battery"  # noqa: S105 -- test credential


async def register(client: AsyncClient, name: str) -> dict:
    response = await client.post(
        "/v1/auth/register",
        json={"email": f"{name}@example.com", "username": name, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    body: dict = response.json()
    return body


async def login(client: AsyncClient, name: str) -> dict:
    response = await client.post("/v1/auth/login", data={"username": name, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def signed_up(client: AsyncClient, name: str) -> dict[str, str]:
    """Register and log in; returns the Authorization header of the new user."""
    await register(client, name)
    return bearer((await login(client, name))["access_token"])
