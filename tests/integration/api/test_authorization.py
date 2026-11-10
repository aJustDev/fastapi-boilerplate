"""Who may touch what: a permission on the route, and ownership of the resource.

Authentication is covered by tests/functional/test_auth_required_on_all_endpoints.py.
A valid token only says who is calling; these tests are about the second user.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, insert, select

from app.auth.models.associations import user_roles
from app.auth.models.role import RoleORM
from app.core.db import async_session_factory
from tests._routes import iter_api_routes
from tests.integration.api.helpers import bearer, login, register, signed_up

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _create_item(client: AsyncClient, headers: dict[str, str], name: str = "mine") -> int:
    response = await client.post("/v1/items", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    item_id: int = response.json()["id"]
    return item_id


async def _set_roles(user_id: int, *names: str) -> None:
    """Replace the roles of a user, the way an administrator or a migration would."""
    async with async_session_factory() as session:
        await session.execute(delete(user_roles).where(user_roles.c.user_id == user_id))
        for name in names:
            role_id = select(RoleORM.id).where(RoleORM.name == name).scalar_subquery()
            await session.execute(insert(user_roles).values(user_id=user_id, role_id=role_id))
        await session.commit()


class TestOwnership:
    async def test_another_users_item_looks_missing(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        item_id = await _create_item(api_client, alice)
        url = f"/v1/items/{item_id}"

        read = await api_client.get(url, headers=bob)
        update = await api_client.patch(url, json={"name": "taken"}, headers=bob)
        remove = await api_client.delete(url, headers=bob)
        absent = await api_client.get("/v1/items/999999", headers=bob)

        assert read.status_code == update.status_code == remove.status_code == 404
        # Same answer as an id nobody has: the response does not confirm that it exists.
        assert read.json()["code"] == absent.json()["code"] == "not_found"
        mine = await api_client.get(url, headers=alice)
        assert mine.status_code == 200
        assert mine.json()["name"] == "mine"

    async def test_lists_show_only_the_callers_items(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        await _create_item(api_client, alice, "of alice")
        bobs = await _create_item(api_client, bob, "of bob")

        offset = await api_client.get("/v1/items", headers=bob)
        cursor = await api_client.get("/v1/items/cursor", headers=bob)
        search = await api_client.get("/v1/items", params={"name": "of"}, headers=bob)

        assert offset.json()["total"] == 1
        assert [i["id"] for i in offset.json()["items"]] == [bobs]
        assert [i["id"] for i in cursor.json()["items"]] == [bobs]
        assert [i["id"] for i in search.json()["items"]] == [bobs]

    async def test_a_query_parameter_cannot_widen_the_list(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        await _create_item(api_client, alice)
        alice_id = (await api_client.get("/v1/auth/me", headers=alice)).json()["id"]

        response = await api_client.get("/v1/items", params={"owner_id": alice_id}, headers=bob)

        assert response.json()["total"] == 0

    async def test_filter_options_come_from_the_callers_items(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        await api_client.post("/v1/items", json={"name": "a", "category": "books"}, headers=alice)
        await api_client.post("/v1/items", json={"name": "b", "category": "sports"}, headers=bob)

        response = await api_client.get("/v1/items/filters", headers=bob)

        assert response.json()["category"] == ["sports"]

    async def test_the_owner_has_full_access(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        url = f"/v1/items/{await _create_item(api_client, alice)}"

        assert (await api_client.get(url, headers=alice)).status_code == 200
        renamed = await api_client.patch(url, json={"name": "renamed"}, headers=alice)
        assert renamed.json()["name"] == "renamed"
        assert (await api_client.delete(url, headers=alice)).status_code == 204
        assert (await api_client.get(url, headers=alice)).status_code == 404


class TestPermissions:
    async def test_a_registered_account_holds_the_user_role(self, api_client: AsyncClient):
        user = await register(api_client, "alice")

        assert [role["name"] for role in user["roles"]] == ["user"]

    async def test_an_account_without_the_permission_gets_403(self, api_client: AsyncClient):
        user = await register(api_client, "alice")
        headers = bearer((await login(api_client, "alice"))["access_token"])
        item_id = await _create_item(api_client, headers)
        await _set_roles(user["id"])  # roles are read on every request: no new login needed

        responses = [
            await api_client.get("/v1/items", headers=headers),
            await api_client.get(f"/v1/items/{item_id}", headers=headers),
            await api_client.post("/v1/items", json={"name": "x"}, headers=headers),
            await api_client.patch(f"/v1/items/{item_id}", json={"name": "x"}, headers=headers),
            await api_client.delete(f"/v1/items/{item_id}", headers=headers),
        ]

        assert [r.status_code for r in responses] == [403] * 5
        assert {r.json()["code"] for r in responses} == {"forbidden"}

    async def test_items_manage_reaches_the_items_of_every_owner(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        item_id = await _create_item(api_client, alice)
        admin_user = await register(api_client, "root")
        await _set_roles(admin_user["id"], "admin")
        admin = bearer((await login(api_client, "root"))["access_token"])

        listed = await api_client.get("/v1/items", headers=admin)
        read = await api_client.get(f"/v1/items/{item_id}", headers=admin)
        removed = await api_client.delete(f"/v1/items/{item_id}", headers=admin)

        assert listed.json()["total"] == 1
        assert read.status_code == 200
        assert removed.status_code == 204


# ── Every route that names a resource ─────────────────────
# How to create, as the given user, the resource each path parameter stands for. A route
# with a parameter that is missing here fails below: add how to build its resource, and
# the route is checked like the rest.
RESOURCES = {"item_id": _create_item}
BODIES = {"PATCH": {"name": "changed by someone else"}, "PUT": {"name": "changed"}, "POST": {}}


def _routes_with_a_resource() -> list[tuple[str, str]]:
    found = set()
    for ctx in iter_api_routes():
        if "{" not in ctx.path:
            continue
        for method in ctx.route.methods - {"HEAD", "OPTIONS"}:
            found.add((method, ctx.path))
    return sorted(found)


async def test_scanner_sees_the_routes_with_a_resource():
    # Canary: without it a change in how routes are exposed would leave zero cases below.
    assert len(_routes_with_a_resource()) >= 3


@pytest.mark.parametrize(("method", "path"), _routes_with_a_resource())
async def test_no_route_serves_the_resource_of_another_user(
    api_client: AsyncClient, method: str, path: str
):
    alice = await signed_up(api_client, "alice")
    bob = await signed_up(api_client, "bob")
    names = [part[1:-1] for part in path.split("/") if part.startswith("{")]
    unknown = set(names) - set(RESOURCES)
    assert not unknown, f"say in RESOURCES how to create the resource of {unknown} for {path}"
    url = path.format(**{name: await RESOURCES[name](api_client, alice) for name in names})

    response = await api_client.request(method, url, json=BODIES.get(method), headers=bob)

    assert response.status_code in (403, 404), (
        f"{method} {path} answered {response.status_code} to a user who does not own the "
        "resource: check ownership in the use case (app/items/services/access.py)."
    )
