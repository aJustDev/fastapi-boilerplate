"""Who may touch what: a permission on the route, and the rules of the resource.

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
from tests.integration.api.workshops import (
    begin,
    create_workshop,
    enroll,
    get_workshop,
    published_workshop,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

EDIT = {"version": 1, "title": "changed by someone else"}


async def _set_roles(user_id: int, *names: str) -> None:
    """Replace the roles of a user, the way an administrator or a migration would."""
    async with async_session_factory() as session:
        await session.execute(delete(user_roles).where(user_roles.c.user_id == user_id))
        for name in names:
            role_id = select(RoleORM.id).where(RoleORM.name == name).scalar_subquery()
            await session.execute(insert(user_roles).values(user_id=user_id, role_id=role_id))
        await session.commit()


async def _organizer_requests(
    client: AsyncClient, headers: dict[str, str], workshop_id: int, enrollment_id: int = 1
) -> dict[str, int]:
    """Status of every request that only whoever runs the workshop may make."""
    url = f"/v1/workshops/{workshop_id}"
    attendance = f"{url}/enrollments/{enrollment_id}/attendance"
    return {
        "edit": (await client.patch(url, json=EDIT, headers=headers)).status_code,
        "list enrollments": (await client.get(f"{url}/enrollments", headers=headers)).status_code,
        "attendance": (
            await client.post(attendance, json={"attended": True}, headers=headers)
        ).status_code,
        "publish": (await client.post(f"{url}/publish", headers=headers)).status_code,
        "cancel": (await client.post(f"{url}/cancel", headers=headers)).status_code,
    }


class TestDrafts:
    async def test_someone_elses_draft_looks_missing(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        draft = await create_workshop(api_client, alice)
        url = f"/v1/workshops/{draft['id']}"

        read = await api_client.get(url, headers=bob)
        absent = await api_client.get("/v1/workshops/999999", headers=bob)
        joined = await enroll(api_client, bob, draft["id"])
        left = await api_client.delete(f"{url}/enrollments/me", headers=bob)
        as_organizer = await _organizer_requests(api_client, bob, draft["id"])

        assert read.status_code == joined.status_code == left.status_code == 404
        assert set(as_organizer.values()) == {404}, as_organizer
        # Same answer as an id nobody has: the response does not confirm that it exists.
        assert read.json()["code"] == absent.json()["code"] == "not_found"
        mine = await get_workshop(api_client, alice, draft["id"])
        assert (mine["status"], mine["title"]) == ("draft", "Intro to pottery")

    async def test_the_list_shows_a_draft_only_to_its_organizer(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        await create_workshop(api_client, alice, title="draft of alice")
        published = await published_workshop(api_client, alice, title="open to all")
        bobs = await create_workshop(api_client, bob, title="draft of bob")

        async def listed(headers: dict[str, str], **params: str) -> list[int]:
            response = await api_client.get("/v1/workshops", params=params, headers=headers)
            return sorted(w["id"] for w in response.json()["items"])

        assert await listed(bob) == sorted([published["id"], bobs["id"]])
        # Asking for drafts, or searching for the title, does not widen what is visible.
        assert await listed(bob, status="draft") == [bobs["id"]]
        assert await listed(bob, q="alice") == []
        assert len(await listed(alice)) == 2


class TestPublishedWorkshops:
    async def test_everyone_sees_it_and_only_its_organizer_runs_it(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        workshop = await published_workshop(api_client, alice)
        enrolled = (await enroll(api_client, alice, workshop["id"])).json()
        await begin(workshop["id"])

        seen = await get_workshop(api_client, bob, workshop["id"])
        as_someone_else = await _organizer_requests(api_client, bob, workshop["id"], enrolled["id"])

        assert seen["id"] == workshop["id"]
        # Visible, so not hidden behind a 404: forbidden.
        assert set(as_someone_else.values()) == {403}, as_someone_else
        unchanged = await get_workshop(api_client, alice, workshop["id"])
        assert (unchanged["title"], unchanged["status"]) == ("Intro to pottery", "published")
        as_organizer = await _organizer_requests(api_client, alice, workshop["id"], enrolled["id"])
        assert as_organizer["list enrollments"] == as_organizer["attendance"] == 200

    async def test_an_enrollment_is_reachable_only_through_its_own_workshop(
        self, api_client: AsyncClient
    ):
        # Bob runs a workshop, so he passes the check on its path. The enrollment he
        # names belongs to a workshop of alice.
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        hers = await published_workshop(api_client, alice)
        his = await published_workshop(api_client, bob)
        enrollment = (await enroll(api_client, alice, hers["id"])).json()
        await begin(hers["id"])
        await begin(his["id"])

        response = await api_client.post(
            f"/v1/workshops/{his['id']}/enrollments/{enrollment['id']}/attendance",
            json={"attended": False},
            headers=bob,
        )

        assert response.status_code == 404
        listed = await api_client.get(f"/v1/workshops/{hers['id']}/enrollments", headers=alice)
        assert [e["status"] for e in listed.json()["items"]] == ["confirmed"]

    async def test_an_enrollment_belongs_to_whoever_made_it(self, api_client: AsyncClient):
        alice = await signed_up(api_client, "alice")
        bob = await signed_up(api_client, "bob")
        workshop = await published_workshop(api_client, alice)
        await enroll(api_client, alice, workshop["id"])

        left = await api_client.delete(
            f"/v1/workshops/{workshop['id']}/enrollments/me", headers=bob
        )
        bobs = await api_client.get("/v1/me/enrollments", headers=bob)
        hers = await api_client.get("/v1/me/enrollments", headers=alice)

        assert left.status_code == 404  # bob has no enrollment; alice's is not his to end
        assert bobs.json()["total"] == 0
        assert [e["status"] for e in hers.json()["items"]] == ["confirmed"]


class TestPermissions:
    async def test_a_registered_account_holds_the_user_role(self, api_client: AsyncClient):
        user = await register(api_client, "alice")

        assert [role["name"] for role in user["roles"]] == ["user"]

    async def test_an_account_without_the_permission_gets_403(self, api_client: AsyncClient):
        user = await register(api_client, "alice")
        headers = bearer((await login(api_client, "alice"))["access_token"])
        workshop = await published_workshop(api_client, headers)
        await _set_roles(user["id"])  # roles are read on every request: no new login needed
        url = f"/v1/workshops/{workshop['id']}"

        responses = [
            await api_client.get("/v1/workshops", headers=headers),
            await api_client.get(url, headers=headers),
            await api_client.patch(url, json=EDIT, headers=headers),
            await api_client.post(f"{url}/enrollments", headers=headers),
            await api_client.get("/v1/me/enrollments", headers=headers),
        ]

        assert [r.status_code for r in responses] == [403] * 5
        assert {r.json()["code"] for r in responses} == {"forbidden"}

    async def test_workshops_moderate_reaches_the_workshops_of_every_organizer(
        self, api_client: AsyncClient
    ):
        alice = await signed_up(api_client, "alice")
        draft = await create_workshop(api_client, alice)
        admin_user = await register(api_client, "root")
        await _set_roles(admin_user["id"], "admin")
        admin = bearer((await login(api_client, "root"))["access_token"])

        listed = await api_client.get("/v1/workshops", headers=admin)
        read = await api_client.get(f"/v1/workshops/{draft['id']}", headers=admin)
        cancelled = await api_client.post(f"/v1/workshops/{draft['id']}/cancel", headers=admin)

        assert [w["id"] for w in listed.json()["items"]] == [draft["id"]]
        assert read.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


# ── Every route that names a resource ─────────────────────
# How to create, as the given user, a private resource for each path parameter: one that
# nobody else may see. A route with a parameter that is missing here fails below: add how
# to build its resource, and the route is checked like the rest.


async def _private_workshop(client: AsyncClient, headers: dict[str, str]) -> int:
    workshop_id: int = (await create_workshop(client, headers))["id"]  # a draft
    return workshop_id


async def _own_enrollment(client: AsyncClient, headers: dict[str, str]) -> int:
    workshop = await published_workshop(client, headers)
    enrollment_id: int = (await enroll(client, headers, workshop["id"])).json()["id"]
    return enrollment_id


RESOURCES = {"workshop_id": _private_workshop, "enrollment_id": _own_enrollment}
BODIES = {"PATCH": EDIT, "PUT": EDIT, "POST": {"attended": True}}


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
        f"{method} {path} answered {response.status_code} to a user who may not see the "
        "resource: check who it belongs to in the use case "
        "(app/workshops/services/access.py)."
    )
