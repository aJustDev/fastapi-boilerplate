"""The workshop routes through HTTP, with the repositories patched: what each route
requires, what it answers and how it serializes it. What is stored and who may touch it
is in tests/integration/api/."""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus
from tests._routes import iter_api_routes
from tests._workshops import enrollment, workshop, workshop_body

REPO = "app.workshops.repos.workshop.WorkshopRepo"
ENROLLMENTS = "app.workshops.repos.enrollment.EnrollmentRepo"
SEATING = "app.workshops.services.seating.SeatingService"


@pytest.fixture
def signed_in(fake_user: MagicMock) -> Iterator[MagicMock]:
    """The caller is `fake_user` (id 1): it holds the user role's permissions."""
    with (
        patch("app.auth.repos.revoked_token.RevokedTokenRepo.is_revoked", return_value=False),
        patch("app.auth.repos.user.UserRepo.get_by_id", return_value=fake_user),
    ):
        yield fake_user


async def _stored(entity, data=None):
    """What `create` and `update` do to an entity, minus the database."""
    for key, value in (data or {}).items():
        setattr(entity, key, value)
    defaults = {"id": 10, "seats_taken": 0, "status": WorkshopStatus.DRAFT, "version": 1}
    for key, value in defaults.items():
        if getattr(entity, key, None) is None:
            setattr(entity, key, value)
    if entity.created_at is None:
        entity.created_at = workshop().created_at
    return entity


class TestCreate:
    async def test_creates_a_draft_organized_by_the_caller(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with patch(f"{REPO}.create", side_effect=_stored):
            response = await client.post(
                "/v1/workshops", json=workshop_body(capacity=12), headers=auth_headers
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["organizer_id"] == signed_in.id
        assert (body["status"], body["capacity"], body["seats_taken"]) == ("draft", 12, 0)
        assert body["version"] == 1

    async def test_an_invalid_workshop_names_what_is_wrong(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        response = await client.post(
            "/v1/workshops", json=workshop_body(capacity=0, title=""), headers=auth_headers
        )

        assert response.status_code == 422
        errors = " ".join(response.json()["errors"])
        assert "body.capacity" in errors
        assert "body.title" in errors


class TestRead:
    async def test_a_published_workshop_of_someone_else(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with patch(f"{REPO}.get_by_id", return_value=workshop(organizer_id=2)):
            response = await client.get("/v1/workshops/10", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["title"] == "Intro to pottery"

    async def test_a_draft_of_someone_else_is_a_404(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        draft = workshop(organizer_id=2, status=WorkshopStatus.DRAFT)
        with patch(f"{REPO}.get_by_id", return_value=draft):
            response = await client.get("/v1/workshops/10", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_the_list_passes_the_query_on_and_returns_the_cursor(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with patch(f"{REPO}.list_cursor", return_value=([workshop()], "next", True)) as listed:
            response = await client.get(
                "/v1/workshops",
                params={"q": "pot", "status": "published", "limit": 1, "order_dir": "desc"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["next_cursor"] == "next"
        assert response.json()["has_more"] is True
        called = listed.call_args.kwargs
        assert (called["limit"], called["order_by"], called["order_dir"]) == (
            1,
            "starts_at",
            "desc",
        )
        assert called["filters"] == {"status": "published", "starts_after": None, "title": "pot"}
        assert called["scope"] is not None  # a plain user does not see every draft


class TestChange:
    async def test_a_stale_version_is_a_409_with_its_code(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with patch(f"{REPO}.get_for_update", return_value=workshop(version=4)):
            response = await client.patch(
                "/v1/workshops/10", json={"version": 3, "title": "New"}, headers=auth_headers
            )

        assert response.status_code == 409
        assert response.json()["code"] == "version_conflict"

    async def test_running_someone_elses_workshop_is_a_403(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with patch(f"{REPO}.get_for_update", return_value=workshop(organizer_id=2)):
            response = await client.post("/v1/workshops/10/cancel", headers=auth_headers)

        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"

    async def test_publishing_twice_is_a_409(self, client: AsyncClient, auth_headers, signed_in):
        with patch(f"{REPO}.get_for_update", return_value=workshop()):
            response = await client.post("/v1/workshops/10/publish", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["code"] == "invalid_state"


class TestEnrollments:
    @pytest.mark.parametrize(("created", "status"), [(True, 201), (False, 200)])
    async def test_a_new_enrollment_is_a_201_and_a_repeat_a_200(
        self, client: AsyncClient, auth_headers, signed_in, created: bool, status: int
    ):
        waiting = enrollment(attendee_id=1, status=EnrollmentStatus.WAITLISTED)
        with (
            patch(f"{REPO}.get_for_update", return_value=workshop(organizer_id=2)),
            patch(f"{SEATING}.enroll", return_value=(waiting, created)),
        ):
            response = await client.post("/v1/workshops/10/enrollments", headers=auth_headers)

        assert response.status_code == status
        assert response.json()["status"] == "waitlisted"
        assert "workshop" not in response.json()

    async def test_leaving_answers_204_without_a_body(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        with (
            patch(f"{REPO}.get_for_update", return_value=workshop(organizer_id=2)),
            patch(f"{ENROLLMENTS}.get_current", return_value=enrollment(attendee_id=1)),
            patch(f"{SEATING}.release") as release,
        ):
            response = await client.delete("/v1/workshops/10/enrollments/me", headers=auth_headers)

        assert (response.status_code, response.content) == (204, b"")
        release.assert_awaited_once()

    async def test_my_enrollments_come_with_their_workshop(
        self, client: AsyncClient, auth_headers, signed_in
    ):
        mine = enrollment(attendee_id=1, workshop=workshop())
        with patch(f"{ENROLLMENTS}.list_paginated", return_value=([mine], 1)) as listed:
            response = await client.get("/v1/me/enrollments", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["workshop"]["title"] == "Intro to pottery"
        assert listed.call_args.kwargs["filters"] == {"attendee_id": 1, "status": None}


# ── The permission of each route ──────────────────────────


def _workshop_routes() -> list[tuple[str, str]]:
    return sorted(
        (method, ctx.path)
        for ctx in iter_api_routes()
        if ctx.path.startswith(("/v1/workshops", "/v1/me/"))
        for method in ctx.route.methods - {"HEAD", "OPTIONS"}
    )


def test_scanner_sees_the_workshop_routes():
    assert len(_workshop_routes()) == 11


@pytest.mark.parametrize(("method", "path"), _workshop_routes())
async def test_every_route_requires_its_permission(
    client: AsyncClient, auth_headers, signed_in, method: str, path: str
):
    # An account with no role: authenticated, and allowed nothing.
    signed_in.has_permission = MagicMock(return_value=False)
    url = path.format(workshop_id=10, enrollment_id=100)

    response = await client.request(method, url, json={}, headers=auth_headers)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    (asked,), _ = signed_in.has_permission.call_args
    assert asked.startswith("workshops:")
