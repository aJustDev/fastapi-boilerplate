"""A workshop from draft to the end, through HTTP and a real database: seats, the waiting
list, and the events each step leaves for the outbox."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.integration.api.helpers import signed_up
from tests.integration.api.workshops import (
    begin,
    create_workshop,
    enroll,
    events,
    get_workshop,
    published_workshop,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _people(client: AsyncClient, *names: str) -> list[dict[str, str]]:
    return [await signed_up(client, name) for name in names]


async def _statuses(client: AsyncClient, organizer: dict[str, str], workshop_id: int) -> list[str]:
    """Enrollment statuses of a workshop in the order people enrolled."""
    response = await client.get(
        f"/v1/workshops/{workshop_id}/enrollments", params={"page_size": 100}, headers=organizer
    )
    assert response.status_code == 200, response.text
    return [e["status"] for e in response.json()["items"]]


async def _event_types() -> list[str]:
    return [event.event_type for event in await events()]


class TestSeats:
    async def test_seats_fill_in_order_and_the_rest_wait(self, api_client: AsyncClient):
        organizer, ana, ben, cai = await _people(api_client, "organizer", "ana", "ben", "cai")
        workshop = await published_workshop(api_client, organizer, capacity=2)

        answers = [await enroll(api_client, who, workshop["id"]) for who in (ana, ben, cai)]

        assert [a.status_code for a in answers] == [201, 201, 201]
        assert [a.json()["status"] for a in answers] == ["confirmed", "confirmed", "waitlisted"]
        assert (await get_workshop(api_client, ana, workshop["id"]))["seats_taken"] == 2
        # Who waits is not told a seat is theirs.
        assert await _event_types() == ["enrollment.confirmed"] * 2

    async def test_enrolling_twice_is_the_same_enrollment(self, api_client: AsyncClient):
        organizer, ana = await _people(api_client, "organizer", "ana")
        workshop = await published_workshop(api_client, organizer)

        first = await enroll(api_client, ana, workshop["id"])
        again = await enroll(api_client, ana, workshop["id"])

        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json() == first.json()
        assert (await get_workshop(api_client, ana, workshop["id"]))["seats_taken"] == 1
        assert await _event_types() == ["enrollment.confirmed"]

    async def test_a_seat_that_is_left_goes_to_the_first_person_waiting(
        self, api_client: AsyncClient
    ):
        organizer, ana, ben, cai = await _people(api_client, "organizer", "ana", "ben", "cai")
        workshop = await published_workshop(api_client, organizer, capacity=1)
        for who in (ana, ben, cai):
            await enroll(api_client, who, workshop["id"])

        left = await api_client.delete(
            f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ana
        )

        assert left.status_code == 204
        assert await _statuses(api_client, organizer, workshop["id"]) == [
            "cancelled",
            "confirmed",  # ben was first in line
            "waitlisted",
        ]
        assert (await get_workshop(api_client, ana, workshop["id"]))["seats_taken"] == 1
        # Both events were stored by the same transaction: found by type, not by order.
        (cancelled,) = await events("enrollment.cancelled")
        (promoted,) = await events("enrollment.promoted")
        assert cancelled.payload["reason"] == "left"
        mine = await api_client.get("/v1/me/enrollments", headers=ben)
        assert promoted.aggregate_id == str(mine.json()["items"][0]["id"])

    async def test_leaving_the_waiting_list_moves_nobody(self, api_client: AsyncClient):
        organizer, ana, ben = await _people(api_client, "organizer", "ana", "ben")
        workshop = await published_workshop(api_client, organizer, capacity=1)
        await enroll(api_client, ana, workshop["id"])
        await enroll(api_client, ben, workshop["id"])

        await api_client.delete(f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ben)

        assert await _statuses(api_client, organizer, workshop["id"]) == ["confirmed", "cancelled"]
        assert (await get_workshop(api_client, ana, workshop["id"]))["seats_taken"] == 1

    async def test_who_left_may_come_back_at_the_end_of_the_line(self, api_client: AsyncClient):
        organizer, ana, ben = await _people(api_client, "organizer", "ana", "ben")
        workshop = await published_workshop(api_client, organizer, capacity=1)
        await enroll(api_client, ana, workshop["id"])
        await enroll(api_client, ben, workshop["id"])
        await api_client.delete(f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ana)

        back = await enroll(api_client, ana, workshop["id"])

        assert (back.status_code, back.json()["status"]) == (201, "waitlisted")
        assert await _statuses(api_client, organizer, workshop["id"]) == [
            "cancelled",
            "confirmed",
            "waitlisted",
        ]

    async def test_leaving_without_an_enrollment_is_a_404(self, api_client: AsyncClient):
        organizer, ana = await _people(api_client, "organizer", "ana")
        workshop = await published_workshop(api_client, organizer)

        left = await api_client.delete(
            f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ana
        )

        assert left.status_code == 404
        assert left.json()["code"] == "not_found"


class TestOrganizerChanges:
    async def test_more_seats_go_to_the_waiting_list_in_order(self, api_client: AsyncClient):
        organizer, ana, ben, cai, dee = await _people(
            api_client, "organizer", "ana", "ben", "cai", "dee"
        )
        workshop = await published_workshop(api_client, organizer, capacity=1)
        for who in (ana, ben, cai, dee):
            await enroll(api_client, who, workshop["id"])

        grown = await api_client.patch(
            f"/v1/workshops/{workshop['id']}", json={"version": 1, "capacity": 3}, headers=organizer
        )

        assert grown.status_code == 200, grown.text
        assert (grown.json()["capacity"], grown.json()["seats_taken"]) == (3, 3)
        assert await _statuses(api_client, organizer, workshop["id"]) == [
            "confirmed",
            "confirmed",
            "confirmed",
            "waitlisted",
        ]
        assert (await _event_types()).count("enrollment.promoted") == 2

    async def test_capacity_cannot_go_below_the_seats_taken(self, api_client: AsyncClient):
        organizer, ana, ben = await _people(api_client, "organizer", "ana", "ben")
        workshop = await published_workshop(api_client, organizer, capacity=2)
        await enroll(api_client, ana, workshop["id"])
        await enroll(api_client, ben, workshop["id"])

        shrunk = await api_client.patch(
            f"/v1/workshops/{workshop['id']}", json={"version": 1, "capacity": 1}, headers=organizer
        )

        assert shrunk.status_code == 409
        assert shrunk.json()["code"] == "capacity_below_enrolled"
        assert (await get_workshop(api_client, organizer, workshop["id"]))["capacity"] == 2

    async def test_an_edit_states_the_version_it_started_from(self, api_client: AsyncClient):
        (organizer,) = await _people(api_client, "organizer")
        workshop = await create_workshop(api_client, organizer)
        url = f"/v1/workshops/{workshop['id']}"

        first = await api_client.patch(
            url, json={"version": 1, "title": "first"}, headers=organizer
        )
        stale = await api_client.patch(url, json={"version": 1, "title": "lost"}, headers=organizer)
        fresh = await api_client.patch(
            url, json={"version": 2, "title": "second"}, headers=organizer
        )

        assert (first.status_code, first.json()["version"]) == (200, 2)
        assert (stale.status_code, stale.json()["code"]) == (409, "version_conflict")
        assert (fresh.json()["title"], fresh.json()["version"]) == ("second", 3)

    async def test_one_new_date_is_checked_against_the_other(self, api_client: AsyncClient):
        (organizer,) = await _people(api_client, "organizer")
        workshop = await create_workshop(api_client, organizer)

        response = await api_client.patch(
            f"/v1/workshops/{workshop['id']}",
            json={"version": 1, "ends_at": workshop["starts_at"]},
            headers=organizer,
        )

        assert response.status_code == 400
        assert response.json()["code"] == "business_validation"

    async def test_the_status_moves_only_along_the_diagram(self, api_client: AsyncClient):
        (organizer,) = await _people(api_client, "organizer")
        workshop = await create_workshop(api_client, organizer)
        url = f"/v1/workshops/{workshop['id']}"

        published = await api_client.post(f"{url}/publish", headers=organizer)
        again = await api_client.post(f"{url}/publish", headers=organizer)
        cancelled = await api_client.post(f"{url}/cancel", headers=organizer)
        reopened = await api_client.post(f"{url}/publish", headers=organizer)
        edited = await api_client.patch(url, json={"version": 1, "title": "x"}, headers=organizer)

        assert (published.json()["status"], cancelled.json()["status"]) == (
            "published",
            "cancelled",
        )
        for refused in (again, reopened, edited):
            assert (refused.status_code, refused.json()["code"]) == (409, "invalid_state")


class TestCancellation:
    async def test_cancelling_ends_every_enrollment_and_tells_each_person(
        self, api_client: AsyncClient
    ):
        organizer, ana, ben, cai = await _people(api_client, "organizer", "ana", "ben", "cai")
        workshop = await published_workshop(api_client, organizer, capacity=2)
        for who in (ana, ben, cai):
            await enroll(api_client, who, workshop["id"])
        await api_client.delete(f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ana)
        before = len(await events())

        cancelled = await api_client.post(
            f"/v1/workshops/{workshop['id']}/cancel",
            headers={**organizer, "X-Request-ID": "cancel-1"},
        )

        assert (cancelled.json()["status"], cancelled.json()["seats_taken"]) == ("cancelled", 0)
        assert await _statuses(api_client, organizer, workshop["id"]) == ["cancelled"] * 3
        # One event for ben and one for cai; ana had left and is not told again.
        told = (await events())[before:]
        assert [e.event_type for e in told] == ["enrollment.cancelled"] * 2
        assert {e.payload["reason"] for e in told} == {"workshop_cancelled"}
        assert {e.correlation_id for e in told} == {"cancel-1"}
        assert len({e.aggregate_id for e in told}) == 2

    async def test_a_cancelled_workshop_takes_nobody(self, api_client: AsyncClient):
        organizer, ana = await _people(api_client, "organizer", "ana")
        workshop = await published_workshop(api_client, organizer)
        await api_client.post(f"/v1/workshops/{workshop['id']}/cancel", headers=organizer)

        response = await enroll(api_client, ana, workshop["id"])

        assert (response.status_code, response.json()["code"]) == (409, "enrollment_closed")


class TestOnceItStarted:
    async def test_nobody_enrols_or_leaves(self, api_client: AsyncClient):
        organizer, ana, ben = await _people(api_client, "organizer", "ana", "ben")
        workshop = await published_workshop(api_client, organizer)
        await enroll(api_client, ana, workshop["id"])
        await begin(workshop["id"])

        late = await enroll(api_client, ben, workshop["id"])
        leaving = await api_client.delete(
            f"/v1/workshops/{workshop['id']}/enrollments/me", headers=ana
        )
        repeat = await enroll(api_client, ana, workshop["id"])

        assert (late.status_code, late.json()["code"]) == (409, "enrollment_closed")
        assert (leaving.status_code, leaving.json()["code"]) == (409, "enrollment_closed")
        assert (repeat.status_code, repeat.json()["status"]) == (200, "confirmed")

    async def test_attendance_is_recorded_and_can_be_corrected(self, api_client: AsyncClient):
        organizer, ana, ben = await _people(api_client, "organizer", "ana", "ben")
        workshop = await published_workshop(api_client, organizer, capacity=1)
        seated = (await enroll(api_client, ana, workshop["id"])).json()
        waiting = (await enroll(api_client, ben, workshop["id"])).json()
        url = f"/v1/workshops/{workshop['id']}/enrollments"

        early = await api_client.post(
            f"{url}/{seated['id']}/attendance", json={"attended": True}, headers=organizer
        )
        await begin(workshop["id"])
        absent = await api_client.post(
            f"{url}/{seated['id']}/attendance", json={"attended": False}, headers=organizer
        )
        present = await api_client.post(
            f"{url}/{seated['id']}/attendance", json={"attended": True}, headers=organizer
        )
        never_seated = await api_client.post(
            f"{url}/{waiting['id']}/attendance", json={"attended": True}, headers=organizer
        )

        assert (early.status_code, early.json()["code"]) == (409, "invalid_state")
        assert (absent.json()["status"], present.json()["status"]) == ("no_show", "attended")
        assert (never_seated.status_code, never_seated.json()["code"]) == (409, "invalid_state")
        # Having attended still counts as the seat it was.
        assert (await get_workshop(api_client, organizer, workshop["id"]))["seats_taken"] == 1


async def test_my_enrollments_show_each_workshop_and_filter_by_status(api_client: AsyncClient):
    organizer, ana = await _people(api_client, "organizer", "ana")
    soon = datetime.now(UTC) + timedelta(days=2)
    first = await published_workshop(api_client, organizer, title="Glazing", capacity=1)
    second = await published_workshop(
        api_client,
        organizer,
        title="Wheel throwing",
        starts_at=soon.isoformat(),
        ends_at=(soon + timedelta(hours=3)).isoformat(),
    )
    await enroll(api_client, organizer, first["id"])  # takes the only seat
    await enroll(api_client, ana, first["id"])
    await enroll(api_client, ana, second["id"])

    everything = await api_client.get("/v1/me/enrollments", headers=ana)
    waiting = await api_client.get(
        "/v1/me/enrollments", params={"status": "waitlisted"}, headers=ana
    )

    assert [(e["workshop"]["title"], e["status"]) for e in everything.json()["items"]] == [
        ("Wheel throwing", "confirmed"),
        ("Glazing", "waitlisted"),
    ]
    assert everything.json()["items"][0]["workshop"]["status"] == "published"
    assert [e["workshop"]["id"] for e in waiting.json()["items"]] == [first["id"]]
    assert waiting.json()["total"] == 1
